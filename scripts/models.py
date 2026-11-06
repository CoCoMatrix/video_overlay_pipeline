"""Resolve existing or public weights on the cloud host, with content receipts."""
import argparse, json, os, sys, urllib.request, shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from media_v3 import digest, atomic_json, identity
REPO=Path(__file__).resolve().parents[1]

def qwen_receipt(path):
    path=Path(path).resolve()
    required=['config.json','model.safetensors.index.json','tokenizer_config.json','tokenizer.json',
              'preprocessor_config.json','video_preprocessor_config.json']
    for n in required:
        if not (path/n).is_file(): raise ValueError('missing model file: '+n)
    if json.loads((path/'config.json').read_text()).get('model_type')!='qwen3_vl':
        raise ValueError('expected Qwen3-VL model_type')
    weights=set(json.loads((path/'model.safetensors.index.json').read_text())['weight_map'].values())
    for n in weights:
        if Path(n).name!=n or not (path/n).is_file():raise ValueError('missing/unsafe weight shard')
    # Content identity includes weights, processor and tokenizer; same-name replacements cannot reuse cache.
    hashes={p.name:digest(p) for p in sorted(path.iterdir()) if p.is_file() and p.suffix in {'.json','.txt','.safetensors'}}
    return {'files':hashes,'identity':identity(hashes)}

def main():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest='mode',required=True)
    for name in ['existing','huggingface']:
        a=sub.add_parser(name);a.add_argument('--root',required=True);a.add_argument('--ocr-model')
        if name=='existing': a.add_argument('--model',required=True)
        else:a.add_argument('--cache-dir',required=True)
    args=p.parse_args();root=Path(args.root).resolve();root.mkdir(parents=True,exist_ok=True)
    if (root/'model-receipt.json').exists():raise ValueError('model already configured; use a new run root')
    cfg=json.loads((REPO/'configs/models.json').read_text())
    if args.mode=='huggingface':
        from huggingface_hub import snapshot_download
        model=Path(snapshot_download(repo_id=cfg['qwen']['repo_id'],revision=cfg['qwen']['revision'],
                   cache_dir=str(Path(args.cache_dir).resolve()),ignore_patterns=['*.md','.gitattributes'])).resolve()
    else:model=Path(args.model).resolve()
    receipt=qwen_receipt(model)
    target=root/'models/Qwen3-VL-8B-Instruct';target.parent.mkdir(exist_ok=True)
    if target.exists() or target.is_symlink():
        if not target.is_symlink() or target.resolve()!=model:raise ValueError('different model link already exists')
    else:target.symlink_to(os.path.relpath(model,target.parent),target_is_directory=True)
    ocrdir=root/'ocr/models';ocrdir.mkdir(parents=True,exist_ok=True)
    ocr=ocrdir/'ch_PP-OCRv5_det_mobile.onnx'
    if args.ocr_model:
        source=Path(args.ocr_model).resolve()
        if digest(source)!=cfg['ocr']['sha256']:raise ValueError('OCR model checksum mismatch')
        if not ocr.exists():ocr.symlink_to(os.path.relpath(source,ocr.parent))
    else:
        temp=ocr.with_suffix('.partial')
        with urllib.request.urlopen(cfg['ocr']['url'],timeout=60) as response,temp.open('wb') as out:shutil.copyfileobj(response,out)
        if digest(temp)!=cfg['ocr']['sha256']:temp.unlink();raise ValueError('OCR download checksum mismatch')
        temp.replace(ocr)
    if digest(ocr)!=cfg['ocr']['sha256']:raise ValueError('configured OCR model checksum mismatch')
    receipt.update(mode=args.mode,source=str(model),upstream=cfg['qwen'] if args.mode=='huggingface' else None,
                   ocr_sha256=digest(ocr),note='existing copy does not imply equality to public upstream')
    atomic_json(root/'model-receipt.json',receipt)
    print('Weights configured:',root,'identity:',receipt['identity'])
if __name__=='__main__':main()
