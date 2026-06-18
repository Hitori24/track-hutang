"""
Personal Expense Manager (Ultimate Edition v2)
==============================================
Features: PIN Protection, Visual Charts, Partial Payments, 
Friend Deletion, Timestamps, and WhatsApp Auto-Reminders.
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
    """Total amount `friend` currently owes the user."""
    direct_total = sum(
        d["amount"] for d in data["direct_debts"]
        if d["friend"] == friend and not d.get("settled", False)
    )
    split_total = sum(
        s["share_per_person"] for s in data["group_splits"]
        if not s.get("settled", False) and friend in s.get("debtors", [])
    )
    return round(direct_total + split_total, 2)

def friend_breakdown(data: dict, friend: str) -> list[tuple[str, float, str]]:
    """Line items behind a friend's balance including dates."""
    items = [
        (d["desc"] or "Direct debt", d["amount"], d.get("date", "Unknown date"))
        for d in data["direct_debts"]
        if d["friend"] == friend and not d.get("settled", False)
    ]
    items += [
        (s["description"] or "Group expense", s["share_per_person"], s.get("date", "Unknown date"))
        for s in data["group_splits"]
        if not s.get("settled", False) and friend in s.get("debtors", [])
    ]
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

def record_partial_payment(data: dict, friend: str, amount: float) -> None:
    """Record a partial repayment as a negative debt to reduce the balance."""
    data["direct_debts"].append({
        "friend": friend,
        "amount": -abs(amount), # Negative amount acts as a payment
        "desc": "Repayment / Partial Settle",
        "settled": False,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M")
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
    total_owed = round(sum(balances.values()), 2)

    col1, col2 = st.columns([1, 1])
    with col1:
        st.metric("Total owed to you", f"RM {total_owed:.2f}")
    
    # 📊 VISUAL CHART
    active_balances = {k: v for k, v in balances.items() if v > 0}
    if active_balances:
        with col2:
            st.caption("Debt Distribution")
            st.bar_chart(active_balances, height=150, color="#FF4B4B")

    st.divider()

    for friend, balance in balances.items():
        if balance > 0:
            col_a, col_b = st.columns([3, 1])
            with col_a:
                st.error(f"🔴  **{friend}** owes you **RM {balance:.2f}**")
                with st.expander(f"Breakdown for {friend}"):
                    for desc, amount, date in friend_breakdown(data, friend):
                        st.write(f"• **{desc}** (_{date}_) — RM {amount:.2f}")
            with col_b:
                msg = f"Hey {friend}! Just a friendly reminder about the RM {balance:.2f} outstanding balance. Thanks! 🙏"
                wa_url = f"https://wa.me/?text={urllib.parse.quote(msg)}"
                st.markdown(f"[💬 Remind via WA]({wa_url})")
        elif balance < 0:
            st.warning(f"🟡  You owe **{friend}** **RM {abs(balance):.2f}**")
        else:
            st.success(f"✅  **{friend}** is all clear")

    st.divider()
    
    st.subheader("🤝 Quick Settle Up")
    debtors = [f for f, b in balances.items() if b > 0]

    if not debtors:
        st.caption("Nobody owes you anything right now.")
        return

    # FIXED: Removed st.form here so the UI dynamically shows the amount input!
    friend_to_settle = st.selectbox("Select friend", debtors)
    settle_type = st.radio("Payment Type", ["Full Settle", "Partial Payment"])
    
    partial_amount = 0.0
    if settle_type == "Partial Payment":
        partial_amount = st.number_input("Amount Paid (RM)", min_value=0.01, step=1.0)
        
    if st.button("Confirm Payment ✅"):
        if settle_type == "Full Settle":
            settle_friend(data, friend_to_settle)
            st.toast(f"All settled up with {friend_to_settle}!", icon="✅")
        else:
            record_partial_payment(data, friend_to_settle, partial_amount)
            st.toast(f"Recorded RM {partial_amount:.2f} repayment from {friend_to_settle}.", icon="✅")
        
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
                # Calculate balance to check if deletion is allowed
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
        friend = st.selectbox("Who owes you?", data["friends"])
        amount = st.number_input("Amount (RM)", min_value=0.0, step=0.01, format="%.2f")
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
                "date": datetime.now().strftime("%Y-%m-%d %H:%M") # Added Timestamp
            })
            persist_state()
            st.success(f"Recorded RM {rounded:.2f} owed by {friend}.")
            st.rerun()

def page_split_bill(data: dict) -> None:
    st.header("🧾 Split a Bill")

    if not data["friends"]:
        st.warning("Add at least one friend before splitting a bill.")
        return

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
                "date": datetime.now().strftime("%Y-%m-%d %H:%M") # Added Timestamp
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
                status = "✅" if d.get("settled", False) else "🔴"
                if d["amount"] < 0:
                    status = "💵" # It's a payment
                date_str = d.get("date", "Unknown date")
                st.write(f"{status} **{d['friend']}** | RM {d['amount']:.2f} | '{d['desc']}' _({date_str})_")
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
                status = "✅" if s.get("settled", False) else "🔴"
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
        return # Stop loading the app if not authenticated
        
    # 2. Initialize session state for robust data handling
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
