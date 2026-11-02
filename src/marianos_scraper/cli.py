"""Operators: check-config and verify do not contact Mariano's or Azure."""
from __future__ import annotations
import argparse
import json
import logging
import os
import sys
import traceback
from datetime import datetime,timezone
from pathlib import Path
from .config import load_categories,load_settings
from .schema import FIELDS,validate
from .runner import Pipeline,slot_id
from .storage import make_storage,Locked

class JsonFormatter(logging.Formatter):
    def format(self,record):
        row={"timestamp":datetime.now(timezone.utc).isoformat(),"level":record.levelname,
             "event":record.getMessage(),"logger":record.name}
        for k in ("store","slot","category","subcategory","items","records","units","sha256","error","url","attempt","proof","count","scrolls","pages","subcategories","displayed_total"):
            if hasattr(record,k):row[k]=getattr(record,k)
        if record.exc_info:row["exception"]=self.formatException(record.exc_info)
        return json.dumps(row,ensure_ascii=False)

def configure_logging():
    h=logging.StreamHandler(sys.stdout);h.setFormatter(JsonFormatter())
    root=logging.getLogger();root.handlers=[h];root.setLevel(logging.INFO)

def require_authorization(authorization_file='',stores=None,categories=None):
    """No browser/API calls without documented rights to bulk collect this retailer data."""
    if os.getenv("MARIANOS_AUTHORIZED", "").lower() not in ("true","1","yes") or not os.getenv("MARIANOS_APPROVAL_REFERENCE", "").strip():
        raise PermissionError("LIVE CRAWL DISABLED. Set MARIANOS_AUTHORIZED=true and MARIANOS_APPROVAL_REFERENCE only after obtaining permission for automated collection and storage. Public API registration alone is not proof.")
    if stores is not None and categories is not None:
        from .qualification import authorization_evidence, _private_evidence_bytes
        path=authorization_file or os.getenv('MARIANOS_AUTHORIZATION_FILE','')
        check=authorization_evidence(path,stores,categories)
        if not check.get('passed'):
            raise PermissionError('LIVE CRAWL DISABLED. Signed authorization evidence unavailable or invalid: '+str(check.get('reason','incomplete scope')))
        if os.environ['MARIANOS_APPROVAL_REFERENCE'].strip()!=check['agreement_id']:
            raise PermissionError('LIVE CRAWL DISABLED. Approval reference must equal the verified agreement ID')
        # This implementation uses the retailer browser. A license for an
        # unrelated API/feed does not confer browser automation rights.
        method=json.loads(_private_evidence_bytes(path).decode('utf-8'))['authorized_access_method']
        if not any(token in str(method).lower() for token in ('browser','website','web site')):
            raise PermissionError('LIVE CRAWL DISABLED. Authorization does not explicitly cover browser/website collection')

def check_export(path:str):
    records=json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(records,list) or not records:raise ValueError("JSON must be a nonempty array")
    for i,row in enumerate(records):
        try:validate(row)
        except Exception as exc:raise ValueError(f"record #{i} failed: {exc}") from exc
    duplicates=len(records)-len({(p["zipcode"],p["store_location"],p["upc"] or p["url"].split("?",1)[0]) for p in records})
    report={"status":"passed" if not duplicates else "failed", "records":len(records),"duplicates":duplicates,
            "field_order":list(FIELDS),"category_counts":dict(__import__("collections").Counter(p["category"] for p in records))}
    return report

def main(argv=None):
    parser=argparse.ArgumentParser(description="Mariano's Azure collection: permission gated and fail-closed")
    parser.add_argument("command",choices=["check-config","run","verify-export","release-check"])
    parser.add_argument("--categories",default="config/Marianos_Category_URLs.csv")
    parser.add_argument("--settings",default="config/stores.yaml")
    parser.add_argument("--store",help="optional configured store id")
    parser.add_argument("--slot",help="date YYYY-MM-DD to resume specific twice-weekly slot")
    parser.add_argument("--force",action="store_true",help="recollect even if current slot already passed")
    parser.add_argument("--file",help="path for verify-export")
    parser.add_argument("--authorization-file",default="",help="local signed authorization metadata JSON")
    parser.add_argument("--azure-proof-file",default="",help="Azure observed execution evidence JSON")
    parser.add_argument("--acceptance-file",default="",help="Independent signed real-world acceptance JSON")
    parser.add_argument("--reviewer-public-key",default="",help="Trusted client reviewer Ed25519 public key PEM")
    args=parser.parse_args(argv)
    configure_logging()
    try:
        if args.command=="release-check":
            from .qualification import release_report
            result=release_report(args.categories,args.settings,args.authorization_file,args.file or "",args.azure_proof_file,
                                  args.acceptance_file,args.reviewer_public_key)
            print(json.dumps(result,indent=2));return 0 if result["status"]=="GO" else 3
        if args.command=="verify-export":
            if not args.file:parser.error("--file required")
            result=check_export(args.file)
            print(json.dumps(result,indent=2));return 0 if result["status"]=="passed" else 1
        categories=load_categories(args.categories)
        stores,options=load_settings(args.settings)
        if args.store:stores=[s for s in stores if s.id==args.store]
        if not stores:raise ValueError(f"store {args.store} not configured")
        if args.command=="check-config":
            result={"status":"valid","categories":len(categories),"category_names":[c.name for c in categories],"stores":[{"id":s.id,"zipcode":s.zipcode,"address":s.address} for s in stores],"schedule":"Monday and Thursday","slot":args.slot or slot_id()}
            print(json.dumps(result,indent=2));return 0
        require_authorization(args.authorization_file,stores,categories)
        storage=make_storage()
        reports=[]
        failures=[]
        for store in stores:
            try:
                reports.append(Pipeline(storage).run(store,categories,options,slot=args.slot,force=args.force))
            except Locked as exc:
                logging.error("overlap_prevented",extra={"store":store.id,"error":str(exc)})
                failures.append({"store":store.id,"type":"overlap","error":str(exc)})
            except Exception as exc:
                logging.error("store_failed",extra={"store":store.id,"error":str(exc)},exc_info=True)
                failures.append({"store":store.id,"type":type(exc).__name__,"error":str(exc)})
        print(json.dumps({"reports":reports,"failures":failures},indent=2))
        return 2 if failures else 0
    except Exception as exc:
        logging.error("command_failed",extra={"error":f"{type(exc).__name__}: {exc}"},exc_info=True)
        return 2

if __name__=="__main__":
    sys.exit(main())