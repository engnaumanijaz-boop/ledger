import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# --- 1. Database Setup ---
def init_db():
    conn = sqlite3.connect('ijaz_ledger.db')
    c = conn.cursor()
    # Table for Jobs (The BL/GD Folders)
    c.execute('''CREATE TABLE IF NOT EXISTS jobs
                 (bl_number TEXT PRIMARY KEY, gd_number TEXT, client_name TEXT, status TEXT)''')
    # Table for Transactions (The specific payments and receipts)
    c.execute('''CREATE TABLE IF NOT EXISTS transactions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  bl_number TEXT, 
                  date TEXT, 
                  trans_type TEXT, 
                  amount REAL,
                  FOREIGN KEY(bl_number) REFERENCES jobs(bl_number))''')
    conn.commit()
    return conn

conn = init_db()

# --- 2. Financial Logic & Queries ---
def get_job_summary():
    query = '''
        SELECT 
            j.bl_number, j.gd_number, j.client_name,
            SUM(CASE WHEN t.trans_type = 'Transfer In' THEN t.amount ELSE 0 END) as total_received,
            SUM(CASE WHEN t.trans_type IN ('Duty', 'DO', 'Terminal', 'LOLO', 'Detention') THEN t.amount ELSE 0 END) as total_expenses,
            SUM(CASE WHEN t.trans_type = 'Bill' THEN t.amount ELSE 0 END) as final_bill
        FROM jobs j
        LEFT JOIN transactions t ON j.bl_number = t.bl_number
        GROUP BY j.bl_number
    '''
    df = pd.read_sql_query(query, conn)
    
    # Financial Best Practice: Calculate WIP (Work In Progress) vs Finalized Profit
    df['cash_balance'] = df['total_received'] - df['total_expenses']
    df['job_status'] = df.apply(lambda row: 'Billed 🟢' if row['final_bill'] > 0 else 'Under Process 🟡', axis=1)
    df['profit_loss'] = df['final_bill'] - df['total_expenses']
    
    return df

# --- 3. Web UI / Dashboard ---
st.set_page_config(page_title="Customs Ledger OS", layout="wide")
st.title("📦 Customs Clearance Ledger")

# Sidebar for Data Entry
st.sidebar.header("Log New Data")
entry_mode = st.sidebar.radio("Action:", ["Log Transaction", "Create New Job"])

if entry_mode == "Create New Job":
    with st.sidebar.form("new_job_form"):
        new_bl = st.text_input("BL Number").strip().upper()
        new_gd = st.text_input("GD Number (Optional)").strip().upper()
        new_client = st.text_input("Client Name (Optional)").strip()
        submit_job = st.form_submit_button("Create Job Folder")
        
        if submit_job and new_bl:
            try:
                conn.cursor().execute("INSERT INTO jobs (bl_number, gd_number, client_name, status) VALUES (?, ?, ?, ?)", 
                                      (new_bl, new_gd, new_client, 'Under Process'))
                conn.commit()
                st.sidebar.success(f"Job {new_bl} created successfully!")
            except sqlite3.IntegrityError:
                st.sidebar.error("BL Number already exists.")

elif entry_mode == "Log Transaction":
    # Get active BLs for dropdown
    bl_list = pd.read_sql_query("SELECT bl_number FROM jobs", conn)['bl_number'].tolist()
    
    with st.sidebar.form("new_trans_form"):
        if not bl_list:
            st.warning("Please create a Job first.")
        else:
            sel_bl = st.selectbox("Select BL Number", bl_list)
            trans_type = st.selectbox("Transaction Type", 
                                      ["Transfer In", "Duty", "DO", "Terminal", "LOLO", "Detention", "Bill"])
            amount = st.number_input("Amount (Rs)", min_value=0.0, step=100.0)
            date_logged = st.date_input("Date", datetime.today())
            submit_trans = st.form_submit_button("Log Amount")
            
            if submit_trans and amount > 0:
                conn.cursor().execute("INSERT INTO transactions (bl_number, date, trans_type, amount) VALUES (?, ?, ?, ?)",
                                      (sel_bl, date_logged.strftime("%Y-%m-%d"), trans_type, amount))
                conn.commit()
                st.sidebar.success(f"Logged Rs {amount:,.0f} for {sel_bl}")

# --- 4. Main Dashboard Views ---
df_summary = get_job_summary()

if not df_summary.empty:
    col1, col2, col3 = st.columns(3)
    
    # Separate Cash Flow from Job Costing
    total_cash_in_bank = df_summary['cash_balance'].sum()
    total_unbilled_expenses = df_summary[df_summary['job_status'] == 'Under Process 🟡']['total_expenses'].sum()
    actual_realized_profit = df_summary[df_summary['job_status'] == 'Billed 🟢']['profit_loss'].sum()
    
    col1.metric("Current Cash Balance", f"Rs {total_cash_in_bank:,.0f}", 
                help="Total Transfers In minus Total Expenses paid out.")
    col2.metric("WIP (Unbilled Outflows)", f"Rs {total_unbilled_expenses:,.0f}", 
                help="Money spent on active GDs waiting to be billed.", delta_color="inverse")
    col3.metric("Realized Profit (Completed Jobs)", f"Rs {actual_realized_profit:,.0f}",
                help="Total Billed minus Total Expenses for closed jobs.")
    
    st.divider()
    
    # Financial Views
    tab1, tab2 = st.tabs(["Active Jobs (Under Process)", "Completed & Billed"])
    
    with tab1:
        st.subheader("Jobs Awaiting Final Invoices")
        active_df = df_summary[df_summary['job_status'] == 'Under Process 🟡'].copy()
        if not active_df.empty:
            st.dataframe(active_df[['bl_number', 'gd_number', 'total_received', 'total_expenses', 'cash_balance']], use_container_width=True)
        else:
            st.info("No active jobs pending billing.")
            
    with tab2:
        st.subheader("Finalized Jobs")
        billed_df = df_summary[df_summary['job_status'] == 'Billed 🟢'].copy()
        if not billed_df.empty:
            st.dataframe(billed_df[['bl_number', 'total_expenses', 'final_bill', 'profit_loss']], use_container_width=True)
        else:
            st.info("No completed jobs yet.")
else:
    st.info("Your ledger is currently empty. Create a Job in the sidebar to begin.")