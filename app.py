"""
Personal Expense Manager (Ultimate Edition v3)
==============================================
Features: PIN Protection, Visual Charts, Partial Payments, 
Friend Deletion, Timestamps, WhatsApp Auto-Reminders, 
and Two-Way Debt Tracking (Money you owe others).
"""

import json
import os
import urllib.parse
from datetime import datetime
import streamlit as st

# --- CONFIGURATION ---
st.set_page_config(page_title="Hutang Manager", page_icon="💸", layout="centered")

# 🔒 SECURITY SETTING: Change your PIN here!
APP_PIN = "1234" 

DATA_FILE = "debts.json"

# --------------------------------------------------------------------------
# Storage & State Management
# --------------------------------------------------------------------------
def load_data() -> dict:
    """Load the JSON database, creating or repairing it if necessary."""
    if not os.path.exists(DATA_FILE):
        return {"friends": [], "direct_debts": [], "group_splits": []}

    try:
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        st.warning("debts.json was unreadable, so it has been reset.")
        return {"friends": [], "direct_debts": [], "group_splits": []}

    # Backfill missing keys
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

def persist_state():
    """Helper to save the current session state to disk."""
    save_data(st.session_state.data)

# --------------------------------------------------------------------------
# Balance logic
# --------------------------------------------------------------------------
def calculate_balance(data: dict, friend: str) -> float:
    """
    Total amount `friend` currently owes the user.
    If positive, they owe user. If negative, user owes them.
    """
    direct_total = sum(
        d["amount"] for d in data["direct_debts"]
        if d["friend"] == friend and not d.get("settled", False)
    )
    split_total = sum(
        s["share_per_person"] for s in data["group_splits"]
        if not s.get("settled", False) and friend in s.get("debtors", [])
    )
    return round(direct_total + split_total, 2)

def friend_breakdown(data: dict, friend: str) -> list[tuple[str, float, str, str]]:
    """Line items behind a friend's balance including dates and transaction type."""
    items = []
    for d in data["direct_debts"]:
        if d["friend"] == friend and not d.get("settled", False):
            # Fallback for old data without 'type'
            ttype = d.get("type", "lent" if d["amount"] >= 0 else "payment_received")
            items.append((d["desc"] or "Direct debt", d["amount"], d.get("date", "Unknown date"), ttype))
            
    for s in data["group_splits"]:
        if not s.get("settled", False) and friend in s.get("debtors", []):
            items.append((s["description"] or "Group expense", s["share_per_person"], s.get("date", "Unknown date"), "split"))
            
    return items

def settle_friend(data: dict, friend: str) -> None:
    """Mark a friend's direct debts settled and drop them from active splits."""
    for d in data["direct_debts"]:
        if d["friend"] == friend:
            d["settled"] = True
    for s in data["group_splits"]:
        if friend in s.get("debtors", []):
            s["debtors"].remove(friend)
            if not s["debtors"]:
                s["settled"] = True

def record_partial_payment(data: dict, friend: str, amount: float, is_user_paying: bool) -> None:
    """Record a partial repayment to reduce the balance."""
    if is_user_paying:
        # User pays friend -> positive amount to offset negative balance
        val = abs(amount)
        ttype = "payment_made"
        desc = "I paid them back (Partial)"
    else:
        # Friend pays user -> negative amount to offset positive balance
        val = -abs(amount)
        ttype = "payment_received"
        desc = "They paid me back (Partial)"
        
    data["direct_debts"].append({
        "friend": friend,
        "amount": val,
        "desc": desc,
        "settled": False,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "type": ttype
    })

# --------------------------------------------------------------------------
# Pages
# --------------------------------------------------------------------------
def page_dashboard(data: dict) -> None:
    st.header("📊 The Balance Sheet")

    if not data["friends"]:
        st.info("No friends yet — add one in **Manage Friends** to get started.")
        return

    balances = {friend: calculate_balance(data, friend) for friend in data["friends"]}
    
    total_receivable = sum(b for b in balances.values() if b > 0)
    total_payable = sum(abs(b) for b in balances.values() if b < 0)

    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        st.metric("You are owed (Incoming)", f"RM {total_receivable:.2f}")
    with col2:
        st.metric("You owe (Outgoing)", f"RM {total_payable:.2f}")
    
    # 📊 VISUAL CHART (Only show incoming debts for the chart)
    active_incoming = {k: v for k, v in balances.items() if v > 0}
    if active_incoming:
        with col3:
            st.bar_chart(active_incoming, height=150, color="#FF4B4B")
    else:
        with col3:
            st.caption("No incoming debts to display.")

    st.divider()

    for friend, balance in balances.items():
        if balance > 0:
            col_a, col_b = st.columns([3, 1])
            with col_a:
                st.error(f"🔴  **{friend}** owes you **RM {balance:.2f}**")
                with st.expander(f"Breakdown for {friend}"):
                    for desc, amount, date, ttype in friend_breakdown(data, friend):
                        if ttype in ["lent", "split"]:
                            st.write(f"• 🔴 Lent: **{desc}** (_{date}_) — RM {abs(amount):.2f}")
                        elif ttype == "payment_received":
                            st.write(f"• 🟢 Received: **{desc}** (_{date}_) — RM {abs(amount):.2f}")
            with col_b:
                msg = f"Hey {friend}! Just a friendly reminder about the RM {balance:.2f} outstanding balance. Thanks! 🙏"
                wa_url = f"https://wa.me/?text={urllib.parse.quote(msg)}"
                st.markdown(f"[💬 Remind via WA]({wa_url})")
                
        elif balance < 0:
            col_a, col_b = st.columns([3, 1])
            with col_a:
                st.warning(f"🟡  You owe **{friend}** **RM {abs(balance):.2f}**")
                with st.expander(f"Breakdown for {friend}"):
                    for desc, amount, date, ttype in friend_breakdown(data, friend):
                        if ttype == "borrowed":
                            st.write(f"• 🟡 Borrowed: **{desc}** (_{date}_) — RM {abs(amount):.2f}")
                        elif ttype == "payment_made":
                            st.write(f"• 🟢 Paid: **{desc}** (_{date}_) — RM {abs(amount):.2f}")
            with col_b:
                st.caption("Don't forget to pay them back! 💸")
                
        elif balance == 0 and calculate_balance(data, friend) == 0:
            # Check if there's history but balance is 0
            if friend_breakdown(data, friend):
                st.success(f"✅  **{friend}** is all clear")

    st.divider()
    
    st.subheader("🤝 Quick Settle Up")
    active_friends = [f for f, b in balances.items() if round(b, 2) != 0.00]

    if not active_friends:
        st.caption("All balances are settled right now.")
        return

    friend_to_settle = st.selectbox("Select friend to settle with", active_friends)
    bal = balances[friend_to_settle]
    
    is_user_paying = False
    if bal > 0:
        st.info(f"**{friend_to_settle}** owes you **RM {bal:.2f}**")
        is_user_paying = False
    else:
        st.info(f"You owe **{friend_to_settle}** **RM {abs(bal):.2f}**")
        is_user_paying = True

    settle_type = st.radio("Payment Type", ["Full Settle", "Partial Payment"])
    
    partial_amount = 0.0
    if settle_type == "Partial Payment":
        partial_amount = st.number_input("Amount Paid (RM)", min_value=0.01, step=1.0)
        
    if st.button("Confirm Payment ✅"):
        if settle_type == "Full Settle":
            settle_friend(data, friend_to_settle)
            st.toast(f"All settled up with {friend_to_settle}!", icon="✅")
        else:
            record_partial_payment(data, friend_to_settle, partial_amount, is_user_paying)
            st.toast(f"Recorded RM {partial_amount:.2f} repayment.", icon="✅")
        
        persist_state()
        st.rerun()

def page_manage_friends(data: dict) -> None:
    st.header("👥 Manage Friends")

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
            persist_state()
            st.success(f"Added {name}.")
            st.rerun()

    st.divider()
    st.subheader("Current Friends Directory")
    if not data["friends"]:
        st.info("No friends added yet.")
    else:
        for friend in data["friends"]:
            col1, col2 = st.columns([4, 1])
            with col1:
                st.write(f"• {friend}")
            with col2:
                bal = calculate_balance(data, friend)
                if bal == 0:
                    if st.button("🗑️ Delete", key=f"del_{friend}"):
                        data["friends"].remove(friend)
                        persist_state()
                        st.rerun()
                else:
                    st.caption("Has balance")

def page_add_debt(data: dict) -> None:
    st.header("📝 Add Direct Debt")

    if not data["friends"]:
        st.warning("Add at least one friend before recording a debt.")
        return

    with st.form("add_debt_form", clear_on_submit=True):
        debt_type = st.radio("Transaction Type", ["I lent them money ➡️", "I borrowed from them ⬅️"])
        friend = st.selectbox("Friend:", data["friends"])
        amount = st.number_input("Amount (RM)", min_value=0.0, step=0.01, format="%.2f")
        desc = st.text_input("Description", placeholder="e.g. Borrowed petrol cash")
        submitted = st.form_submit_button("Add Debt")

    if submitted:
        if amount <= 0:
            st.warning("Amount must be greater than zero.")
        else:
            if debt_type == "I borrowed from them ⬅️":
                val = -abs(round(amount, 2))
                ttype = "borrowed"
                success_msg = f"Recorded that you owe RM {abs(val):.2f} to {friend}."
            else:
                val = abs(round(amount, 2))
                ttype = "lent"
                success_msg = f"Recorded RM {val:.2f} owed by {friend}."

            data["direct_debts"].append({
                "friend": friend,
                "amount": val,
                "desc": desc.strip() or "Direct debt",
                "settled": False,
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "type": ttype
            })
            persist_state()
            st.success(success_msg)
            st.rerun()

def page_split_bill(data: dict) -> None:
    st.header("🧾 Split a Bill")

    if not data["friends"]:
        st.warning("Add at least one friend before splitting a bill.")
        return
        
    st.caption("Assume you paid the bill upfront, and friends owe you their share.")

    total_bill = st.number_input("Total bill amount (RM)", min_value=0.0, step=0.01, format="%.2f", key="split_total")
    desc = st.text_input("Description", placeholder="e.g. Mamak Dinner", key="split_desc")
    selected_friends = st.multiselect("Who's splitting this with you?", data["friends"], key="split_friends")

    num_people = len(selected_friends) + 1  
    share = round(total_bill / num_people, 2) if total_bill > 0 else 0.0

    if selected_friends and total_bill > 0:
        st.info(f"Splitting between {num_people} people (including you) → **RM {share:.2f}** each")

    if st.button("Split Bill", type="primary"):
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
                "date": datetime.now().strftime("%Y-%m-%d %H:%M")
            })
            persist_state()
            for key in ("split_total", "split_desc", "split_friends"):
                del st.session_state[key]
            st.success(f"Split saved — {len(selected_friends)} friend(s) each owe RM {share:.2f}.")
            st.rerun()

def page_history(data: dict) -> None:
    st.header("📜 Transaction History")
    
    st.subheader("Direct Debts & Payments")
    if not data["direct_debts"]:
        st.info("No direct debts recorded.")
    else:
        for idx, d in enumerate(reversed(data["direct_debts"])):
            real_idx = len(data["direct_debts"]) - 1 - idx
            col1, col2 = st.columns([5, 1])
            with col1:
                ttype = d.get("type", "lent" if d["amount"] >= 0 else "payment_received")
                
                if d.get("settled", False):
                    status = "✅ Settled"
                else:
                    if ttype == "lent": status = "🔴 (They owe you)"
                    elif ttype == "borrowed": status = "🟡 (You owe them)"
                    elif ttype == "payment_received": status = "🟢 (You received)"
                    elif ttype == "payment_made": status = "🟢 (You paid)"
                    else: status = "⚪"
                    
                date_str = d.get("date", "Unknown date")
                st.write(f"{status} **{d['friend']}** | RM {abs(d['amount']):.2f} | '{d['desc']}' _({date_str})_")
            with col2:
                if st.button("Delete", key=f"del_d_{real_idx}"):
                    data["direct_debts"].pop(real_idx)
                    persist_state()
                    st.rerun()

    st.divider()
    st.subheader("Group Splits")
    if not data["group_splits"]:
        st.info("No group splits recorded.")
    else:
        for idx, s in enumerate(reversed(data["group_splits"])):
            real_idx = len(data["group_splits"]) - 1 - idx
            col1, col2 = st.columns([5, 1])
            with col1:
                status = "✅ Settled" if s.get("settled", False) else "🔴 Active"
                debtors_str = ", ".join(s.get("debtors", []))
                date_str = s.get("date", "Unknown date")
                st.write(f"{status} **RM {s['total_bill']:.2f}** for '{s['description']}' _({date_str})_")
                st.caption(f"Pending from: {debtors_str}")
            with col2:
                if st.button("Delete", key=f"del_s_{real_idx}"):
                    data["group_splits"].pop(real_idx)
                    persist_state()
                    st.rerun()

# --------------------------------------------------------------------------
# App shell, Security, & Navigation
# --------------------------------------------------------------------------
PAGES = {
    "📊 Dashboard": page_dashboard,
    "📝 Add Direct Debt": page_add_debt,
    "🧾 Split a Bill": page_split_bill,
    "👥 Manage Friends": page_manage_friends,
    "📜 History & Edit": page_history,
}

def check_password():
    """Returns True if the user has entered the correct PIN."""
    if st.session_state.get("authenticated", False):
        return True

    st.markdown("<h1 style='text-align: center;'>🔒 Hutang Manager Locked</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center;'>Enter your PIN to access your financial data.</p>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            pin_input = st.text_input("PIN Code", type="password", placeholder="Enter 1234")
            submitted = st.form_submit_button("Unlock 🔓", use_container_width=True)
            
            if submitted:
                if pin_input == APP_PIN:
                    st.session_state["authenticated"] = True
                    st.rerun()
                else:
                    st.error("❌ Incorrect PIN. Try again.")
    return False

def main() -> None:
    # 1. Enforce PIN Security
    if not check_password():
        return 
        
    # 2. Initialize session state
    if "data" not in st.session_state:
        st.session_state.data = load_data()
        
    data = st.session_state.data

    # 3. Render Sidebar
    st.sidebar.title("💸 Hutang Manager")
    choice = st.sidebar.radio("Navigate", list(PAGES.keys()))
    st.sidebar.divider()
    
    # --- CLOUD BACKUP SYSTEM ---
    st.sidebar.subheader("💾 Backup Data")
    
    json_str = json.dumps(data, indent=2)
    st.sidebar.download_button(
        label="⬇️ Export Backup (.json)",
        data=json_str,
        file_name=f"hutang_backup_{datetime.now().strftime('%Y%m%d')}.json",
        mime="application/json",
        use_container_width=True
    )
    
    uploaded_file = st.sidebar.file_uploader("⬆️ Restore Backup", type=["json"])
    if uploaded_file is not None:
        try:
            imported_data = json.load(uploaded_file)
            st.session_state.data = imported_data
            persist_state()
            st.sidebar.success("✅ Restored!")
            st.rerun()
        except Exception:
            st.sidebar.error("Invalid file format.")
            
    if st.sidebar.button("🔒 Lock App", use_container_width=True):
        st.session_state["authenticated"] = False
        st.rerun()

    # 4. Render selected page
    PAGES[choice](data)

if __name__ == "__main__":
    main()
