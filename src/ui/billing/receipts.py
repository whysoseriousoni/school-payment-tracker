from datetime import timedelta

import pandas as pd
import streamlit as st

from data_management.dto.payment import VoidRequest
from data_management.services import payment_service
from helper.clock import today_ist
from reports.receipt import render_receipt_html
from ui.common import flash, page_header, require_user, run_action, rupees

user = require_user()
page_header("Receipts", "Find any receipt to reprint it" + (" or void it." if user.is_admin else "."))

c1, c2, c3 = st.columns([2, 1, 1])
receipt_no = c1.text_input("Receipt number", placeholder="RCPT/2026-27/00012")
date_from = c2.date_input("From", value=today_ist() - timedelta(days=30), format="DD/MM/YYYY")
date_to = c3.date_input("To", value=today_ist(), max_value=today_ist(), format="DD/MM/YYYY")

if receipt_no.strip():
    found = payment_service.find_by_receipt_no(receipt_no)
    receipts = [found] if found else []
else:
    receipts = payment_service.list_payments(date_from=date_from, date_to=date_to)

if not receipts:
    st.info("No receipts found.")
    st.stop()

active = [p for p in receipts if not p.is_voided]
st.caption(f"{len(receipts)} receipts · {rupees(sum(p.amount_paise for p in active))} collected "
           f"(excluding {len(receipts) - len(active)} void)")
st.dataframe(pd.DataFrame([{
    "Receipt": p.receipt_no, "Date": p.paid_on, "Student": p.student_name, "Class": f"{p.student_class}-{p.section}",
    "Amount": rupees(p.amount_paise), "Mode": p.payment_method, "Reference": p.payment_notes,
    "By": p.collected_by, "Status": f"VOID: {p.void_reason}" if p.is_voided else ""} for p in receipts]),
    hide_index=True, width="stretch")

chosen = st.selectbox("Open receipt", receipts, format_func=lambda p: f"{p.receipt_no} - {p.student_name} - "
                      f"{rupees(p.amount_paise)}" + (" (VOID)" if p.is_voided else ""))
with st.container(border=True):
    st.markdown(f"**{chosen.receipt_no}** · {chosen.paid_on:%d %b %Y} · {chosen.student_name} "
                f"({chosen.admission_no}) · Class {chosen.student_class}-{chosen.section}")
    for allocation in chosen.allocations:
        st.markdown(f"- {allocation.label}: {rupees(allocation.amount_paise)}")
    st.markdown(f"**Total {rupees(chosen.amount_paise)}** — {chosen.amount_in_words}")
    st.download_button("Download / print", render_receipt_html(chosen),
                       file_name=f"{chosen.receipt_no.replace('/', '-')}.html", mime="text/html")
    if chosen.is_voided:
        st.error(f"Voided by {chosen.voided_by} on {chosen.voided_on:%d %b %Y}: {chosen.void_reason}")
    elif user.is_admin:
        with st.form(f"void_{chosen.id}", clear_on_submit=True):
            reason = st.text_input("Reason for voiding")
            if st.form_submit_button("Void receipt"):
                if run_action(payment_service.void_payment, VoidRequest(payment_id=chosen.id, reason=reason),
                              user.username):
                    flash(f"Receipt {chosen.receipt_no} voided.", "warning")
                    st.rerun()
