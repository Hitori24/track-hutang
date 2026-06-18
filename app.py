import streamlit as st
import json
import os
import urllib.parse
from datetime import datetime

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Hutang & Splitwise Tracker",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

DB_FILE = "debts.json"

# --- DATABASE OPERATIONS ---
def load_data():
    # If file exists, load it
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                data = json.load(f)
                # Ensure all required keys exist
                if "friends" not in data: data["friends"] = []
                if "direct_debts" not in data: data["direct_debts"] = []
                if "group_splits" not in data: data["group_splits"] = []
                return data
        except Exception:
            pass
    return {"friends": [], "direct_debts": [], "group_splits": []}

def save_data(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

# Initialize Session State
if "data" not in st.session_state:
    st.session_state.data = load_data()

# Helper to save session state back to file
def persist_state():
    save_data(st.session_state.data)

# --- UI HEADER ---
st.markdown("""
<div style="text-align: center; margin-bottom: 20px;">
    <h1 style="color: #FF4B4B; margin-bottom: 0;">💰 Personal Hutang & Splitwise</h1>
    <p style="color: #666; font-size: 1.1rem;">Stop forgetting who owes you money. Track, split, and remind with style!</p>
</div>
""", unsafe_allow_html=True)

# --- SIDEBAR: NAVIGATION & BACKUP SYSTEM ---
st.sidebar.title("⚙️ Control Panel")
menu = st.sidebar.radio(
    "Navigation", 
    ["📊 Dashboard", "👥 Manage Friends", "💸 Add Direct Debt", "🍕 Split a Group Bill", "📜 Transaction History"]
)

st.sidebar.markdown("---")
st.sidebar.subheader("💾 Cloud Cloud Backup & Restore")
st.sidebar.info("Streamlit Cloud resets occasionally. Download backups to save your records locally!")

# Export Backup
json_str = json.dumps(st.session_state.data, indent=4)
st.sidebar.download_button(
    label="⬇️ Export Backup (JSON)",
    data=json_str,
    file_name=f"hutang_backup_{datetime.now().strftime('%Y%m%d')}.json",
    mime="application/json",
    use_container_width=True
)

# Import Backup
uploaded_file = st.sidebar.file_uploader("⬆️ Restore from Backup", type=["json"])
if uploaded_file is not None:
    try:
        imported_data = json.load(uploaded_file)
        if all(k in imported_data for k in ("friends", "direct_debts", "group_splits")):
            st.session_state.data = imported_data
            persist_state()
            st.sidebar.success("✅ Backup restored successfully!")
            st.rerun()
        else:
            st.sidebar.error("❌ Invalid backup file format.")
    except Exception as e:
        st.sidebar.error(f"❌ Error loading file: {e}")

# --- MAIN ENGINE LOGIC ---
friends_list = st.session_state.data["friends"]

# --- SIDE ACTIONS: DYNAMIC BALANCE SHEET CALCULATOR ---
balances = {friend: 0.0 for friend in friends_list}

# Calculate direct debts
for d in st.session_state.data["direct_debts"]:
    if not d.get("settled", False):
        balances[d["friend"]] += d["amount"]
        
# Calculate group splits
for s in st.session_state.data["group_splits"]:
    if not s.get("settled", False):
        for debtor in s["debtors"]:
            if debtor in balances:
                balances[debtor] += s["share_per_person"]

total_receivable = sum(balances.values())

# ==================== MENU: DASHBOARD ====================
if menu == "📊 Dashboard":
    # 1. Metric Callout Row
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(label="Total Outstanding Balance", value=f"RM {total_receivable:.2f}", delta="Money coming back!")
    with col2:
        active_debtors = sum(1 for b in balances.values() if b > 0)
        st.metric(label="Active Debtors", value=f"{active_debtors} Friend(s)")
    with col3:
        if balances:
            biggest_debtor = max(balances, key=balances.get)
            max_amount = balances[biggest_debtor]
            if max_amount > 0:
                st.metric(label="👑 Hall of Shame Leader", value=biggest_debtor, delta=f"RM {max_amount:.2f}")
            else:
                st.metric(label="👑 Hall of Shame Leader", value="None 🎉")
        else:
            st.metric(label="👑 Hall of Shame Leader", value="None 🎉")

    st.markdown("### 📋 Outstanding Balances")
    if not friends_list:
        st.info("Your dashboard is currently empty. Head over to **Manage Friends** to start adding your group!")
    else:
        # Display cards for each friend
        for friend in friends_list:
            balance = balances[friend]
            card_col1, card_col2, card_col3 = st.columns([2, 2, 3])
            
            with card_col1:
                st.markdown(f"#### 👤 {friend}")
            with card_col2:
                if balance > 0:
                    st.markdown(f"<h4 style='color: #FF4B4B; margin: 0;'>RM {balance:.2f}</h4>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<h4 style='color: #00C0F2; margin: 0;'>All Clear 🥳</h4>", unsafe_allow_html=True)
            
            with card_col3:
                if balance > 0:
                    # WhatsApp Auto-Remind System
                    message = f"Hey {friend}! Just a friendly reminder about the RM {balance:.2f} outstanding balance. Thanks! 🙏"
                    encoded_msg = urllib.parse.quote(message)
                    wa_url = f"https://wa.me/?text={encoded_msg}"
                    st.markdown(f"[💬 Send WhatsApp Reminder]({wa_url})")
            st.markdown("---")

        # Quick Settle Section
        st.markdown("### 🤝 Quick Settle Up")
        unsettled_debtors = [f for f, b in balances.items() if b > 0]
        if unsettled_debtors:
            settle_friend = st.selectbox("Select who paid you back:", unsettled_debtors)
            if st.button(f"Mark {settle_friend} as Fully Settled ✅", use_container_width=True):
                # Settle direct debts
                for d in st.session_state.data["direct_debts"]:
                    if d["friend"] == settle_friend:
                        d["settled"] = True
                # Remove friend from active group splits
                for s in st.session_state.data["group_splits"]:
                    if settle_friend in s["debtors"]:
                        s["debtors"].remove(settle_friend)
                        
                persist_state()
                st.success(f"Awesome! All records for {settle_friend} have been marked as settled.")
                st.rerun()
        else:
            st.write("Nobody owes you anything right now! Kick back and relax. 😎")

# ==================== MENU: MANAGE FRIENDS ====================
elif menu == "👥 Manage Friends":
    st.subheader("👥 Friend Directory")
    
    col1, col2 = st.columns([2, 1])
    with col1:
        new_friend = st.text_input("Enter Friend's Name:", placeholder="e.g., Ali, Bala, Chong")
        if st.button("Add New Friend", use_container_width=True):
            clean_name = new_friend.strip()
            if not clean_name:
                st.warning("Please enter a valid name!")
            elif clean_name in friends_list:
                st.error("That friend is already in your directory!")
            else:
                st.session_state.data["friends"].append(clean_name)
                persist_state()
                st.success(f"Added {clean_name} to friends list!")
                st.rerun()
                
    with col2:
        st.markdown("**Your Current Directory:**")
        if friends_list:
            for i, f in enumerate(friends_list, 1):
                st.write(f"{i}. {f}")
        else:
            st.caption("No friends added yet.")

# ==================== MENU: ADD DIRECT DEBT ====================
elif menu == "💸 Add Direct Debt":
    st.subheader("💸 Record an IOU")
    
    if not friends_list:
        st.warning("⚠️ You need to add friends first before you can log debts!")
    else:
        friend = st.selectbox("Who borrowed money from you?", friends_list)
        amount = st.number_input("Amount (RM)", min_value=0.01, step=1.0, format="%.2f")
        desc = st.text_input("Reason / Note:", placeholder="e.g., Petrol cash, cinema tickets")
        
        if st.button("Save Transaction Log", use_container_width=True):
            if not desc:
                st.error("Please specify what the loan was for.")
            else:
                st.session_state.data["direct_debts"].append({
                    "id": len(st.session_state.data["direct_debts"]) + 1,
                    "friend": friend,
                    "amount": round(amount, 2),
                    "desc": desc,
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "settled": False
                })
                persist_state()
                st.success(f"Success! Recorded RM {amount:.2f} owed by {friend}.")

# ==================== MENU: SPLIT A BILL ====================
elif menu == "🍕 Split a Group Bill":
    st.subheader("🍕 Smart Splitwise Engine")
    st.write("Pay the bill upfront, select who was with you, and let the app handle the division!")

    if not friends_list:
        st.warning("⚠️ You need to add friends first before splitting expenses!")
    else:
        total_bill = st.number_input("Total Amount Paid (RM)", min_value=0.01, step=1.0, format="%.2f")
        desc = st.text_input("Group Expense Description:", placeholder="e.g., Mamak dinner, karaoke night")
        
        st.write("**Who was part of this expense with you?**")
        selected_debtors = []
        
        # Display grid of checkboxes
        cols = st.columns(3)
        for idx, friend in enumerate(friends_list):
            with cols[idx % 3]:
                if st.checkbox(friend, key=f"split_{friend}"):
                    selected_debtors.append(friend)

        st.markdown("---")
        if selected_debtors:
            total_people = len(selected_debtors) + 1  # Selected friends + user
            share = round(total_bill / total_people, 2)
            st.info(f"💡 Split Summary: Total {total_people} people. Each friend owes you: **RM {share:.2f}** (Your share: RM {share:.2f})")
            
            if st.button("Post Split to Ledger", use_container_width=True):
                if not desc:
                    st.error("Please add a description for the expense.")
                else:
                    st.session_state.data["group_splits"].append({
                        "id": len(st.session_state.data["group_splits"]) + 1,
                        "description": desc,
                        "total_bill": round(total_bill, 2),
                        "share_per_person": share,
                        "debtors": selected_debtors,
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "settled": False
                    })
                    persist_state()
                    st.success("🎉 Group expense posted and calculated!")
                    st.rerun()
        else:
            st.caption("Check at least one friend above to view split metrics.")

# ==================== MENU: TRANSACTION HISTORY ====================
elif menu == "📜 Transaction History":
    st.subheader("📜 Detailed Ledgers")
    
    tab1, tab2 = st.tabs(["💸 Direct Loans", "🍕 Group Split History"])
    
    with tab1:
        direct_debts = st.session_state.data["direct_debts"]
        if not direct_debts:
            st.info("No direct loan transactions logged yet.")
        else:
            for idx, d in enumerate(direct_debts):
                status = "✅ Settled" if d.get("settled", False) else "🔴 Unpaid"
                status_color = "green" if d.get("settled", False) else "red"
                
                col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
                with col1:
                    st.markdown(f"**{d['desc']}** ({d.get('date', 'N/A')})")
                with col2:
                    st.write(f"Borrower: **{d['friend']}**")
                with col3:
                    st.markdown(f"Amount: **RM {d['amount']:.2f}** | <span style='color:{status_color}'>{status}</span>", unsafe_allow_html=True)
                with col4:
                    if st.button("🗑️", key=f"del_direct_{idx}"):
                        direct_debts.pop(idx)
                        persist_state()
                        st.rerun()
                st.markdown("<hr style='margin:0.5em 0;'>", unsafe_allow_html=True)

    with tab2:
        group_splits = st.session_state.data["group_splits"]
        if not group_splits:
            st.info("No split histories logged yet.")
        else:
            for idx, s in enumerate(group_splits):
                active_debtors = s.get("debtors", [])
                status = "✅ Fully Settled" if not active_debtors else f"🔴 Active (Owed by: {', '.join(active_debtors)})"
                
                col1, col2, col3 = st.columns([4, 4, 1])
                with col1:
                    st.markdown(f"**{s['description']}** ({s.get('date', 'N/A')})")
                    st.caption(f"Total: RM {s['total_bill']:.2f} | Share per Person: RM {s['share_per_person']:.2f}")
                with col2:
                    st.write(f"Status: {status}")
                with col3:
                    if st.button("🗑️", key=f"del_split_{idx}"):
                        group_splits.pop(idx)
                        persist_state()
                        st.rerun()
                st.markdown("<hr style='margin:0.5em 0;'>", unsafe_allow_html=True)
