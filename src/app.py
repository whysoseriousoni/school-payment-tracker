import streamlit as st

from helper.utils import get_or_default
from ui.login import get_user_details

st.set_page_config(layout="wide")

is_authenticated = get_or_default(dictionary=st.session_state, key="LOGGED_IN", default=False)
is_admin = get_or_default(dictionary=st.session_state, key="ADMIN_FLAG", default=False)
whoami = get_or_default(dictionary=st.session_state, key="USER_TYPE", default=False)

### Model registry call
from data_management.sql_manager import create_and_register_sqlite
create_and_register_sqlite()

# if not is_authenticated:
#     get_user_details()
#     st.stop()


from st_pages import get_nav_from_toml
nav = get_nav_from_toml(".streamlit/pages.toml")
pg = st.navigation(nav)
pg.run()
