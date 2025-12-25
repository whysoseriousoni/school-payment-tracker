from st_pages import get_nav_from_toml
import streamlit as st

from helper.utils import get_or_default
from ui.login import get_user_details

st.set_page_config(layout="wide")


is_authenticated = get_or_default(dictionary=st.session_state, key="LOGGED_IN", default=False)
is_admin = get_or_default(dictionary=st.session_state, key="ADMIN_FLAG", default=False)
whoami = get_or_default(dictionary=st.session_state, key="USER_TYPE", default=False)

# if not is_authenticated:
#     get_user_details()
#     st.stop()

nav = get_nav_from_toml(".streamlit/pages.toml")
pg = st.navigation(nav)
pg.run()
