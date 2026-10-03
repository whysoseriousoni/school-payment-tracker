"""Printable fee receipt (self-contained HTML, prints cleanly on A5 / A4)."""
from html import escape
from typing import Dict

from data_management.dto.payment import PaymentRead
from data_management.services import settings_service
from helper.money import format_inr

_STYLE = """
@page { size: A5; margin: 12mm; }
body { font-family: Arial, Helvetica, sans-serif; color: #1E2A35; margin: 0; padding: 16px; }
.receipt { max-width: 640px; margin: 0 auto; border: 1px solid #9FB3C8; padding: 20px 24px; }
header { text-align: center; border-bottom: 2px solid #1F5F8B; padding-bottom: 10px; margin-bottom: 14px; }
header h1 { font-size: 20px; margin: 0; color: #1F5F8B; }
header p { margin: 2px 0; font-size: 12px; }
h2 { font-size: 15px; text-align: center; margin: 0 0 12px; letter-spacing: .5px; }
.meta { width: 100%; font-size: 13px; border-collapse: collapse; margin-bottom: 12px; }
.meta td { padding: 3px 4px; vertical-align: top; }
.meta td.k { color: #52606D; width: 28%; }
table.items { width: 100%; border-collapse: collapse; font-size: 13px; }
table.items th, table.items td { border: 1px solid #C9D5E1; padding: 6px 8px; }
table.items th { background: #EEF3F8; text-align: left; }
td.amt { text-align: right; white-space: nowrap; }
tr.total td { font-weight: bold; background: #EEF3F8; }
.words { font-size: 13px; margin: 10px 0; }
.void { color: #B42318; border: 2px solid #B42318; padding: 6px; text-align: center; font-weight: bold; margin-bottom: 10px; }
footer { display: flex; justify-content: space-between; font-size: 12px; margin-top: 34px; }
.print { text-align: center; margin: 14px; }
@media print { .print { display: none; } body { padding: 0; } .receipt { border: none; } }
"""


def render_receipt_html(payment: PaymentRead, school: Dict[str, str] = None) -> str:
    school = school or settings_service.get_settings()
    e = lambda value: escape(str(value)) if value not in (None, "") else "-"  # noqa: E731
    rows = "".join(
        f"<tr><td>{e(item.label)}</td><td class='amt'>{format_inr(item.amount_paise)}</td></tr>"
        for item in payment.allocations
    )
    void_banner = (
        f"<div class='void'>VOID - {e(payment.void_reason)} (by {e(payment.voided_by)}, "
        f"{payment.voided_on:%d %b %Y})</div>" if payment.is_voided and payment.voided_on else ""
    )
    reference = f" ({e(payment.payment_notes)})" if payment.payment_notes else ""
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Receipt {e(payment.receipt_no)}</title>
<style>{_STYLE}</style></head>
<body><div class="receipt">
<header><h1>{e(school.get(settings_service.SCHOOL_NAME))}</h1>
<p>{e(school.get(settings_service.SCHOOL_ADDRESS))}</p><p>{e(school.get(settings_service.SCHOOL_PHONE))}</p></header>
<h2>FEE RECEIPT</h2>{void_banner}
<table class="meta">
<tr><td class="k">Receipt No</td><td><b>{e(payment.receipt_no)}</b></td><td class="k">Date</td><td>{payment.paid_on:%d %b %Y}</td></tr>
<tr><td class="k">Student</td><td>{e(payment.student_name)}</td><td class="k">Admission No</td><td>{e(payment.admission_no)}</td></tr>
<tr><td class="k">Class</td><td>{e(payment.student_class)}-{e(payment.section)}</td><td class="k">Term</td><td>{e(payment.academic_year_label)}</td></tr>
<tr><td class="k">Received from</td><td>{e(payment.billing_name)}</td><td class="k">Mode</td><td>{e(payment.payment_method)}{reference}</td></tr>
</table>
<table class="items"><tr><th>Particulars</th><th class="amt">Amount</th></tr>{rows}
<tr class="total"><td>Total</td><td class="amt">{format_inr(payment.amount_paise)}</td></tr></table>
<p class="words"><b>In words:</b> {e(payment.amount_in_words)}</p>
{f"<p class='words'><b>Notes:</b> {e(payment.notes)}</p>" if payment.notes else ""}
<footer><span>Collected by: {e(payment.collected_by)}</span><span>Authorised signatory</span></footer>
</div><div class="print"><button onclick="window.print()">Print receipt</button></div></body></html>"""
