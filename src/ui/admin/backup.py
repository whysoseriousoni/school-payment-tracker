import streamlit as st

from backup_and_restore import service
from config import settings
from data_management.services import identifier_crypto
from helper.clock import now_ist
from ui.common import flash, logout, page_header, require_user, run_action

user = require_user(admin_only=True)
page_header("Backup & restore", f"Automatic backups run every {settings.AUTO_BACKUP_INTERVAL_DAYS} days while the "
                                f"app is running; the latest {settings.AUTO_BACKUP_KEEP} are kept.")

tab_backup, tab_restore, tab_key = st.tabs(["Backup", "Restore", "Encryption key"])

with tab_backup:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### Database backup (.db)")
        st.caption("Exact copy. Use this to restore.")
        if st.button("Create backup now", type="primary"):
            path = run_action(service.create_backup, "manual")
            if path:
                flash(f"Backup saved: {path.name}")
                st.rerun()
    with c2:
        st.markdown("##### Excel backup (.xlsx)")
        st.caption("Every table on its own sheet - readable in Excel, and restorable.")
        if st.button("Prepare Excel backup"):
            content = run_action(service.export_excel_backup)
            if content:
                st.download_button("Download Excel backup", content, type="primary",
                                   file_name=f"school_backup_{now_ist():%Y%m%d_%H%M}.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    st.markdown("##### Saved backups")
    backups = service.list_backups()
    if not backups:
        st.caption("No backups yet.")
    for item in backups[:15]:
        b1, b2, b3 = st.columns([4, 1, 1])
        b1.write(f"{item.name}  \n{item.created:%d %b %Y %H:%M} · {item.size_kb} KB")
        b2.download_button("Download", item.path.read_bytes(), file_name=item.name, key=f"dl_{item.name}")
        if service.email_configured() and b3.button("E-mail", key=f"mail_{item.name}"):
            if run_action(lambda: service.send_backup_email([item.path]) or True):
                st.success(f"Sent to {settings.BACKUP_EMAIL_TO}")
    if not service.email_configured():
        st.caption("E-mail delivery is off. Set SPT_SMTP_HOST, SPT_SMTP_USER, SPT_SMTP_PASSWORD and "
                   "SPT_BACKUP_EMAIL_TO to enable it (see README).")

with tab_restore:
    st.warning("Restoring replaces ALL current data. A safety backup of the current data is taken first.")
    upload = st.file_uploader("Backup file", type=["db", "xlsx"])
    confirm = st.text_input("Type RESTORE to confirm")
    if st.button("Restore", type="primary", disabled=upload is None or confirm.strip() != "RESTORE"):
        content = upload.getvalue()
        restore = service.restore_from_excel if upload.name.lower().endswith(".xlsx") else service.restore_from_db_file
        result = run_action(restore, content)
        if result:
            logout()
            flash(f"Restore complete ({sum(result.rows.values())} rows). Safety backup: "
                  f"{result.safety_backup.name}. Please log in again.")
            st.rerun()

with tab_key:
    path = identifier_crypto.key_path()
    st.markdown(
        "Full Aadhaar numbers are encrypted with this key. **Database backups do not contain the key**, so keep a "
        "copy of it somewhere safe and separate (e.g. a USB drive in the office safe). Without it, stored Aadhaar "
        "numbers cannot be read after a restore on a new computer; everything else still works.")
    st.write(f"Key file: `{path}`")
    if path.exists():
        st.write(f"Key ID: `{identifier_crypto.key_fingerprint()}`")
        if st.checkbox("I understand this file must be stored securely"):
            st.download_button("Download key file", path.read_bytes(), file_name="identifier.key")
    else:
        st.caption("The key is created automatically the first time a full Aadhaar number is saved.")
