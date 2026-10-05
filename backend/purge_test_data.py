import os
import sys
import sqlite3

def purge():
    db_path = os.path.join(os.path.dirname(__file__), "fira_local.db")
    if not os.path.exists(db_path):
        print("No fira_local.db found.")
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print("[TABLES PRESENT]:", tables)

    # Tables to clear for a clean slate
    target_tables = [
        "match", "exception", "ap_line", "zimra_line",
        "supplier_action", "supplier", "engagement_metric",
        "report_artifact", "import_batch", "mapping_profile",
        "engagement", "client_branch", "client", "audit_log"
    ]

    for t in target_tables:
        if t in tables:
            cur.execute(f"DELETE FROM {t}")
            print(f"  - Cleared table '{t}'")

    conn.commit()
    conn.close()
    print("[SUCCESS] All test and client data purged completely.")

if __name__ == "__main__":
    purge()
