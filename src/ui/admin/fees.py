import pandas as pd
import streamlit as st

from data_management.dto.fee import FeeAssignment, FeePlanInput, MilestoneInput, MilestoneSet, fee_type_label
from data_management.services import academic_year_service, fee_service
from statics import ANNUAL_FEE_TYPES, CLASSES, SECTIONS, STUDENT_CATEGORY
from ui.common import error_text, flash, optional_select, page_header, require_user, run_action, rupee_input, rupees, term_select

ANY = "Any"
NEW_PLAN = "➕ New plan"

user = require_user(admin_only=True)
page_header("Fee plans", "Annual fees per term. Parents pay in any number of instalments; the payment milestones "
                         "decide what counts as overdue.")
years = academic_year_service.list_years()
term = term_select(key="fees_term", years=years)
if term is None:
    st.stop()

tab_plans, tab_assign, tab_milestones, tab_copy = st.tabs(
    ["Plans", "Assign to students", "Payment milestones", "Copy to another term"])

# ------------------------------------------------------------------ plans
with tab_plans:
    plans = fee_service.list_plans(term.id)
    if plans:
        st.dataframe(pd.DataFrame([{
            "Code": p.code, "Fee": fee_type_label(p.fee_type), "Class": p.student_class or ANY,
            "Category": p.category or ANY, "Annual fee": rupees(p.annual_amount_paise),
            "Default": "✔" if p.is_default else "", "Active": "✔" if p.is_active else "✖",
            "Students": p.students_assigned, "Description": p.description} for p in plans]),
            hide_index=True, width="stretch")
    else:
        st.info(f"No fee plans for {term.label} yet. Add one below, or copy them from another term.")
    st.caption("A **default** plan is given automatically to new and promoted students of that class "
               "(and category, if set). A category-specific default (e.g. DG 1) wins over an 'Any' default.")

    chosen = st.selectbox("Add or edit", [NEW_PLAN] + plans, key=f"fees_edit_pick_{term.id}",
                          format_func=lambda p: p if isinstance(p, str) else p.label)
    plan = None if isinstance(chosen, str) else chosen
    with st.form(f"fees_plan_form_{term.id}_{plan.id if plan else 'new'}"):
        c1, c2, c3, c4 = st.columns(4)
        code = c1.text_input("Code", value=plan.code if plan else "", placeholder="e.g. UKG-FEE-1")
        fee_types = [t.value for t in ANNUAL_FEE_TYPES]
        fee_type = c2.selectbox("Fee", fee_types, format_func=fee_type_label,
                                index=fee_types.index(plan.fee_type) if plan else 0)
        class_options = [ANY] + CLASSES
        plan_class = c3.selectbox("Class (required for tuition)", class_options,
                                  index=class_options.index(plan.student_class) if plan and plan.student_class else 0)
        category_options = [ANY] + STUDENT_CATEGORY
        category = c4.selectbox("Category", category_options,
                                index=category_options.index(plan.category) if plan and plan.category else 0)
        d1, d2, d3, d4 = st.columns([1.5, 1, 1, 3])
        with d1:
            amount = rupee_input("Annual fee", key=f"fees_amount_{term.id}_{plan.id if plan else 'new'}",
                                 value_paise=plan.annual_amount_paise if plan else 0)
        is_default = d2.checkbox("Default", value=plan.is_default if plan else False)
        is_active = d3.checkbox("Active", value=plan.is_active if plan else True)
        description = d4.text_input("Description", value=(plan.description or "") if plan else "",
                                    placeholder="e.g. Sibling concession")
        submitted = st.form_submit_button("Save plan", type="primary")
    if submitted:
        data = run_action(lambda: FeePlanInput(
            academic_year_id=term.id, code=code, fee_type=fee_type,
            student_class=None if plan_class == ANY else plan_class, category=None if category == ANY else category,
            annual_amount_paise=amount, is_default=is_default, is_active=is_active, description=description))
        result = run_action(fee_service.save_plan, data, plan.id if plan else None) if data else None
        if result:
            message = f"Saved {result.plan.code}."
            if result.dues_updated:
                message += f" Updated the fee of {result.dues_updated} students on this plan."
            flash(message)
            if result.dues_skipped:
                flash("Not changed (already paid more than the new amount): " + ", ".join(result.dues_skipped),
                      "warning")
            st.rerun()
    if plan and plan.students_assigned == 0:
        if st.button(f"Delete {plan.code}", key=f"fees_delete_{plan.id}"):
            if run_action(lambda: fee_service.delete_plan(plan.id) or True):
                flash(f"Deleted {plan.code}.", "warning")
                st.rerun()
    elif plan:
        st.caption(f"{plan.code} is used by {plan.students_assigned} students; untick Active to stop using it.")

# ------------------------------------------------------------------ assignment
with tab_assign:
    f1, f2, f3 = st.columns(3)
    with f1:
        a_class = optional_select("Class", CLASSES, key="fees_assign_class")
    with f2:
        a_section = optional_select("Section", SECTIONS, key="fees_assign_section")
    with f3:
        a_category = optional_select("Category", STUDENT_CATEGORY, key="fees_assign_category")

    if st.button("Assign default plans to students without tuition", type="primary"):
        result = run_action(fee_service.assign_defaults, term.id, a_class)
        if result is not None:
            flash(f"Assigned default plans to {result['assigned']} students.")
            if result["missing"]:
                flash("No default plan matches: " + "; ".join(result["missing"]) +
                      ". Add a default plan for that class/category, or assign one below.", "warning")
            st.rerun()

    rows = fee_service.assignment_rows(term.id, a_class, a_section, a_category)
    unassigned = sum(1 for r in rows if r.tuition_paise is None)
    if unassigned:
        st.warning(f"{unassigned} of {len(rows)} students have no tuition fee for {term.label}.")
    st.caption("Select one or more students, then choose a plan or a custom amount below.")
    event = st.dataframe(pd.DataFrame([{
        "Name": r.name, "Admission no": r.admission_no, "Class": f"{r.student_class}-{r.section}",
        "Roll": r.roll_no, "Category": r.category,
        "Tuition plan": r.tuition_plan or ("custom" if r.tuition_paise is not None else "⚠ none"),
        "Tuition": rupees(r.tuition_paise) if r.tuition_paise is not None else "",
        "Paid": rupees(r.tuition_paid_paise), "Van": f"{r.van_plan or 'custom'} {rupees(r.van_paise)}"
        if r.van_paise is not None else ""} for r in rows]),
        hide_index=True, width="stretch", on_select="rerun", selection_mode="multi-row",
        key=f"fees_assign_rows_{term.id}")
    selected = [rows[i] for i in event.selection.rows]

    if selected:
        st.markdown(f"**{len(selected)} selected:** " + ", ".join(r.name for r in selected[:8])
                    + (" ..." if len(selected) > 8 else ""))
        assign_type = st.radio("Fee", [t.value for t in ANNUAL_FEE_TYPES], format_func=fee_type_label,
                               horizontal=True, key="fees_assign_type")
        mode = st.radio("Assign", ["A fee plan", "A custom amount"], horizontal=True, key="fees_assign_mode")
        with st.form("fees_assign_form"):
            if mode == "A fee plan":
                options = fee_service.list_plans(term.id, fee_type=assign_type, active_only=True)
                picked = st.selectbox("Plan", options, format_func=lambda p: f"{p.label} - {rupees(p.annual_amount_paise)}")
                custom, reason = None, None
            else:
                picked = None
                custom = rupee_input("Annual amount", key="fees_assign_custom")
                reason = st.text_input("Reason (required)", placeholder="e.g. Staff child, management approval")
            go = st.form_submit_button(f"Assign to {len(selected)} students", type="primary")
        if go:
            if mode == "A fee plan" and picked is None:
                st.error(f"There is no active {fee_type_label(assign_type)} plan for {term.label}.")
            else:
                done, failed = 0, []
                for row in selected:
                    try:
                        fee_service.assign(FeeAssignment(
                            enrollment_id=row.enrollment_id, fee_type=assign_type,
                            fee_plan_id=picked.id if picked else None, custom_amount_paise=custom, reason=reason))
                        done += 1
                    except Exception as error:  # report per student, keep going
                        failed.append(f"{row.name}: {error_text(error)}")
                if done:
                    flash(f"Assigned to {done} students.")
                for message in failed:
                    flash(message, "error")
                st.rerun()

# ------------------------------------------------------------------ milestones
with tab_milestones:
    st.markdown("Set how much of each annual fee should be paid by each date. Example: **50% by 31 Oct** and "
                "**100% by 31 Mar**. Before the first date nobody is overdue; at the end of the term the whole fee "
                "is expected. One-off fees (books, uniform) are expected as soon as they are added.")
    current = fee_service.get_milestones(term.id)
    table = pd.DataFrame({  # explicit dtypes: an empty table must still be editable as dates / whole numbers
        "Due date": pd.Series(pd.to_datetime([m.due_date for m in current]), dtype="datetime64[ns]"),
        "Cumulative % paid": pd.Series([m.cumulative_percent for m in current], dtype="Int64"),
    })
    edited = st.data_editor(table, num_rows="dynamic", hide_index=True, width="stretch",
                            key=f"fees_milestones_{term.id}", column_config={
                                "Due date": st.column_config.DateColumn(min_value=term.start_date,
                                                                        max_value=term.end_date, format="DD MMM YYYY",
                                                                        required=True),
                                "Cumulative % paid": st.column_config.NumberColumn(min_value=1, max_value=100,
                                                                                   step=1, required=True)})
    if st.button("Save milestones", type="primary"):
        rows = edited.dropna(how="any")
        data = run_action(lambda: MilestoneSet(academic_year_id=term.id, milestones=[
            MilestoneInput(due_date=pd.Timestamp(row["Due date"]).date(),
                           cumulative_percent=int(row["Cumulative % paid"]))
            for row in rows.to_dict("records")]))
        if data and run_action(lambda: fee_service.save_milestones(data) or True):
            flash(f"Saved {len(data.milestones)} milestones for {term.label}.")
            st.rerun()

# ------------------------------------------------------------------ copy
with tab_copy:
    sources = [y for y in years if y.id != term.id]
    if not sources:
        st.caption("There is no other term to copy from yet.")
    else:
        with st.form("fees_copy"):
            source = st.selectbox("Copy plans and milestones from", sources, format_func=lambda y: y.label)
            increase = st.number_input("Increase amounts by (%)", min_value=0.0, max_value=100.0, value=0.0, step=1.0)
            st.caption(f"Plans whose code already exists in {term.label} are left unchanged. Amounts are rounded to "
                       "the nearest rupee. Milestones are copied only if this term has none.")
            if st.form_submit_button(f"Copy into {term.label}", type="primary"):
                copied = run_action(fee_service.copy_plans, source.id, term.id, increase)
                if copied is not None:
                    flash(f"Copied {copied} plans from {source.label}.")
                    st.rerun()
