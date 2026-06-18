"""
Personal Expense Manager
=========================
A single-file Streamlit app combining a Direct Debt Tracker (simple IOUs)
with a Splitwise-style group bill splitter. All data is persisted to a
local JSON file (debts.json) that lives next to this script.

Note: on Streamlit Community Cloud the filesystem is ephemeral, so
debts.json resets whenever the app restarts or redeploys. For durable
hosted storage, swap load_data/save_data for a real database.

Run locally with:
    streamlit run app.py
"""

import json
import os

import streamlit as st

DATA_FILE = "debts.json"


# --------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------

def load_data() -> dict:
    """Load the JSON database, creating or repairing it if necessary."""
    if not os.path.exists(DATA_FILE):
        data = {"friends": [], "direct_debts": [], "group_splits": []}
        save_data(data)
        return data

    try:
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        st.warning("debts.json was unreadable, so it has been reset.")
        data = {"friends": [], "direct_debts": [], "group_splits": []}
        save_data(data)
        return data

    # Backfill any missing keys so older or partially-written files still work.
    data.setdefault("friends", [])
    data.setdefault("direct_debts", [])
    data.setdefault("group_splits", [])
    return data


def save_data(data: dict) -> None:
    """Persist the database to disk."""
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except OSError as e:
        st.error(f"Could not save to {DATA_FILE}: {e}")


# --------------------------------------------------------------------------
# Balance logic
# --------------------------------------------------------------------------

def calculate_balance(data: dict, friend: str) -> float:
    """Total amount `friend` currently owes the user, across both ledgers."""
    direct_total = sum(
        d["amount"] for d in data["direct_debts"]
        if d["friend"] == friend and not d["settled"]
    )
    split_total = sum(
        s["share_per_person"] for s in data["group_splits"]
        if not s["settled"] and friend in s["debtors"]
    )
    return round(direct_total + split_total, 2)


def friend_breakdown(data: dict, friend: str) -> list[tuple[str, float]]:
    """Line items behind a friend's balance, for the dashboard expander."""
    items = [
        (d["desc"] or "Direct debt", d["amount"])
        for d in data["direct_debts"]
        if d["friend"] == friend and not d["settled"]
    ]
    items += [
        (s["description"] or "Group expense", s["share_per_person"])
        for s in data["group_splits"]
        if not s["settled"] and friend in s["debtors"]
    ]
    return items


def settle_friend(data: dict, friend: str) -> None:
    """Mark a friend's direct debts settled and drop them from active splits."""
    for d in data["direct_debts"]:
        if d["friend"] == friend:
            d["settled"] = True
    for s in data["group_splits"]:
        if friend in s["debtors"]:
            s["debtors"].remove(friend)
            if not s["debtors"]:
                s["settled"] = True


# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------

def page_dashboard(data: dict) -> None:
    st.header("The Balance Sheet")

    if not data["friends"]:
        st.info("No friends yet — add one in **Manage Friends** to get started.")
        return

    balances = {friend: calculate_balance(data, friend) for friend in data["friends"]}
    total_owed = round(sum(balances.values()), 2)

    st.metric("Total owed to you", f"${total_owed:.2f}")
    st.divider()

    for friend, balance in balances.items():
        if balance > 0:
            st.error(f"🔴  **{friend}** owes you **${balance:.2f}**")
            with st.expander(f"Breakdown for {friend}"):
                for desc, amount in friend_breakdown(data, friend):
                    st.write(f"• {desc} — ${amount:.2f}")
        else:
            st.success(f"✅  **{friend}** is all clear")

    st.divider()
    st.subheader("Quick Settle Up")
    debtors = [f for f, b in balances.items() if b > 0]

    if not debtors:
        st.caption("Nobody owes you anything right now.")
        return

    with st.form("settle_up_form"):
        friend_to_settle = st.selectbox("Mark this friend as settled up", debtors)
        submitted = st.form_submit_button("Settle Up")

    if submitted:
        settle_friend(data, friend_to_settle)
        save_data(data)
        st.success(f"All settled up with {friend_to_settle}.")
        st.rerun()


def page_manage_friends(data: dict) -> None:
    st.header("Manage Friends")

    with st.form("add_friend_form", clear_on_submit=True):
        new_friend = st.text_input("Friend's name")
        submitted = st.form_submit_button("Add Friend")

    if submitted:
        name = new_friend.strip()
        existing_lower = [f.lower() for f in data["friends"]]
        if not name:
            st.warning("Enter a name before adding.")
        elif name.lower() in existing_lower:
            st.warning(f"{name} is already on your friends list.")
        else:
            data["friends"].append(name)
            save_data(data)
            st.success(f"Added {name}.")
            st.rerun()

    st.subheader("Current Friends")
    if data["friends"]:
        for friend in data["friends"]:
            st.write(f"• {friend}")
    else:
        st.info("No friends added yet.")


def page_add_debt(data: dict) -> None:
    st.header("Add Direct Debt")
    st.caption("IOU Tracker")

    if not data["friends"]:
        st.warning("Add at least one friend before recording a debt.")
        return

    with st.form("add_debt_form", clear_on_submit=True):
        friend = st.selectbox("Who owes you?", data["friends"])
        amount = st.number_input("Amount ($)", min_value=0.0, step=0.01, format="%.2f")
        desc = st.text_input("Description", placeholder="e.g. Borrowed petrol cash")
        submitted = st.form_submit_button("Add Debt")

    if submitted:
        if amount <= 0:
            st.warning("Amount must be greater than zero.")
        else:
            rounded = round(amount, 2)
            data["direct_debts"].append({
                "friend": friend,
                "amount": rounded,
                "desc": desc.strip() or "Direct debt",
                "settled": False,
            })
            save_data(data)
            st.success(f"Recorded ${rounded:.2f} owed by {friend}.")
            st.rerun()


def page_split_bill(data: dict) -> None:
    st.header("Split a Bill")
    st.caption("Splitwise Engine")

    if not data["friends"]:
        st.warning("Add at least one friend before splitting a bill.")
        return

    # These widgets are deliberately NOT inside a form, so the share-per-person
    # preview below updates live as the user types/selects.
    total_bill = st.number_input(
        "Total bill amount ($)", min_value=0.0, step=0.01, format="%.2f", key="split_total"
    )
    desc = st.text_input(
        "Description", placeholder="e.g. Mamak Dinner", key="split_desc"
    )
    selected_friends = st.multiselect(
        "Who's splitting this with you?", data["friends"], key="split_friends"
    )

    num_people = len(selected_friends) + 1  # +1 for the user
    share = round(total_bill / num_people, 2) if total_bill > 0 else 0.0

    if selected_friends and total_bill > 0:
        st.caption(f"Splitting between {num_people} people (including you) → **${share:.2f}** each")

    if st.button("Split Bill"):
        if total_bill <= 0:
            st.warning("Enter a bill amount greater than zero.")
        elif not selected_friends:
            st.warning("Select at least one friend to split with.")
        else:
            data["group_splits"].append({
                "description": desc.strip() or "Group expense",
                "total_bill": round(total_bill, 2),
                "share_per_person": share,
                "debtors": list(selected_friends),
                "settled": False,
            })
            save_data(data)
            # Reset the (non-form) widgets so the next split starts fresh.
            for key in ("split_total", "split_desc", "split_friends"):
                del st.session_state[key]
            st.success(f"Split saved — {len(selected_friends)} friend(s) each owe ${share:.2f}.")
            st.rerun()


# --------------------------------------------------------------------------
# App shell
# --------------------------------------------------------------------------

PAGES = {
    "📊 Dashboard": page_dashboard,
    "👥 Manage Friends": page_manage_friends,
    "📝 Add Direct Debt": page_add_debt,
    "🧾 Split a Bill": page_split_bill,
}


def main() -> None:
    st.set_page_config(page_title="Expense Manager", page_icon="💸", layout="centered")
    data = load_data()

    st.sidebar.title("💸 Expense Manager")
    choice = st.sidebar.radio("Navigate", list(PAGES.keys()))
    st.sidebar.divider()
    st.sidebar.caption(f"{len(data['friends'])} friend(s) tracked")

    PAGES[choice](data)


if __name__ == "__main__":
    main()
