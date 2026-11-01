"""One staging-only provider check; no household data or inventory writes."""
import os
from app.lookup import fetch_product
os.environ["OFF_STAGING"] = "1"
if not os.environ.get("OFF_STAGING_AUTH"):
    raise SystemExit("Set OFF_STAGING_AUTH in your private environment before this optional staging check.")
outcome, fields = fetch_product("3274080005003")
print({"provider": "Open Food Facts staging", "outcome": outcome,
       "name": fields.get("name") if fields else None,
       "nutrition_cached": bool(fields and fields.get("nutrition_json"))})
if outcome != "found":
    raise SystemExit(1)
