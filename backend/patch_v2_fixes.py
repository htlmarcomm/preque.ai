"""
Safe, additive-only patch for EXISTING installs whose CompanyField table is already
seeded (so routers/company_data.py's seed_htl_data() will no longer run and would
never pick up the new MSME field or the new "head office" alias on its own).

This script only ADDS a field if it's missing, and only APPENDS an alias if it's not
already present -- it never deletes, overwrites, or touches any existing row.
Safe to run multiple times (idempotent).

Usage (from the backend/ directory, with your existing preque.db in place):
    python patch_v2_fixes.py
"""
from models.database import SessionLocal, CompanyField

def run():
    db = SessionLocal()
    try:
        # 1. Add the MSME Registration No. field if it doesn't already exist.
        existing = db.query(CompanyField).filter(CompanyField.field_key == "msme_reg_no").first()
        if not existing:
            db.add(CompanyField(
                category="Registration & Legal",
                field_key="msme_reg_no",
                field_label="MSME Registration No.",
                value="",
                aliases=["MSME No", "MSME No.", "MSME Registration Number", "Udyam Registration Number", "Udyam No"],
            ))
            print("Added new field: MSME Registration No. (value left blank -- please fill it in via Company Data)")
        else:
            print("MSME Registration No. field already exists -- left untouched")

        # 2. Append "head office" / "head office address" aliases to the existing
        #    address field, if present, without disturbing anything else on it.
        address_field = db.query(CompanyField).filter(CompanyField.field_key == "address").first()
        if address_field:
            current_aliases = list(address_field.aliases or [])
            added = []
            for new_alias in ["head office", "head office address"]:
                if new_alias not in current_aliases:
                    current_aliases.append(new_alias)
                    added.append(new_alias)
            if added:
                address_field.aliases = current_aliases
                print(f"Appended new aliases to 'address' field: {added}")
            else:
                print("'address' field already had the 'head office' aliases -- left untouched")
        else:
            print("No existing 'address' field found -- nothing to patch there")

        db.commit()
        print("Patch complete. No existing data was modified or deleted.")
    finally:
        db.close()

if __name__ == "__main__":
    run()
