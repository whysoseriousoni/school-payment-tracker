"""
Entry point:  streamlit run app.py

Startup (once per server process): logging, schema migrations, current
academic year, weekly backup scheduler. Navigation is built per role.
"""
import streamlit as st

from backup_and_restore.scheduler import start_backup_scheduler
from data_management.migrations.runner import MigrationError, run_pending_migrations
from data_management.services import academic_year_service
from helper.logger import configure_logging, get_logger
from ui.common import current_user, logout
from ui.login import login_page

st.set_page_config(page_title="School Fee Tracker", page_icon="🏫", layout="wide")


@st.cache_resource(show_spinner="Preparing database...")
def initialise_application() -> bool:
    configure_logging()
    logger = get_logger(__name__)
    for migration in run_pending_migrations():
        logger.info("Applied migration %03d - %s", migration.version, migration.name)
    academic_year_service.ensure_current_year()
    start_backup_scheduler()
    return True


try:
    initialise_application()
except MigrationError as error:
    st.error(
        "The database could not be upgraded, so the app has stopped to protect your data. "
        "Nothing was changed, and a backup was saved in data_store/backups."
    )
    st.exception(error)
    st.stop()

user = current_user()
if user is None:
    st.navigation([st.Page(login_page, title="Login", icon="🔐")]).run()
    st.stop()

pages = {
    "Main": [
        st.Page("ui/home.py", title="Home", icon="🏠", default=True),
        st.Page("ui/account.py", title="My account", icon="👤"),
    ],
    "Students": [
        st.Page("ui/student/students.py", title="Students", icon="🧑‍🎓"),
        st.Page("ui/student/guardians.py", title="Guardians", icon="👪"),
    ],
    "Billing": [
        st.Page("ui/billing/billing.py", title="Collect fees", icon="💵"),
        st.Page("ui/billing/receipts.py", title="Receipts", icon="🧾"),
    ],
    "Analytics": [
        st.Page("ui/analytics/summary.py", title="Summary", icon="📊"),
        st.Page("ui/reports/reports.py", title="Excel reports", icon="📑"),
    ],
}
if user.is_admin:
    pages["Admin"] = [
        st.Page("ui/admin/setup.py", title="Terms & fees", icon="⚙️"),
        st.Page("ui/admin/promotion.py", title="Promotion", icon="🎓"),
        st.Page("ui/admin/users.py", title="Users", icon="🔑"),
        st.Page("ui/admin/backup.py", title="Backup & restore", icon="💾"),
    ]

with st.sidebar:
    st.markdown(f"**{user.username}** · {user.role.title()}")
    if st.button("Log out", width="stretch"):
        logout()
        st.rerun()

st.navigation(pages).run()
