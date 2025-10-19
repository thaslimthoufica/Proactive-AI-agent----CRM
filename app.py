import streamlit as st
import pandas as pd
import boto3
import json
from datetime import datetime, timedelta
from io import BytesIO 

# =========================================================================
# 1. STREAMLIT PAGE CONFIGURATION (MUST BE THE VERY FIRST ST COMMAND)
# =========================================================================
st.set_page_config(
    page_title="Bedrock Contract Expiration Analyzer",
    layout="wide"
)

# --- Configuration Constants ---
# NOTE: App Runner will handle credentialing, but region must be set.
AWS_REGION = 'us-east-1' 
BEDROCK_MODEL_ID = 'anthropic.claude-3-sonnet-20240229-v1:0' 
ALERT_DAYS_THRESHOLD = 90 

# --- Column Name Mapping (Must match your Excel file exactly) ---
# 'Warranty Expiry' is mapped to 'expiry_date' for the primary LLM filter.
COLUMN_MAPPING = {
    'Customer Name': 'company',         
    'Product': 'name',                  
    'Warranty Expiry': 'expiry_date',   
    'Maintenance Expiry': 'service_expiry_date', 
}

# =========================================================================
# 2. CORE BACKEND FUNCTIONS
# =========================================================================

@st.cache_resource
def get_bedrock_client(region):
    """Initializes and returns the Bedrock client. 
    
    In App Runner, this automatically assumes the IAM Role attached to the service.
    """
    try:
        # Boto3 detects the App Runner IAM Role credentials automatically
        return boto3.client(service_name='bedrock-runtime', region_name=region)
    except Exception as e:
        # If this fails, the IAM Role lacks Bedrock permissions.
        st.error(f"Failed to initialize AWS Bedrock Client. Please ensure the App Runner IAM Role has the 'bedrock:InvokeModel' permission. Error: {e}")
        st.stop()
        
bedrock_client = get_bedrock_client(AWS_REGION)


def read_uploaded_file(uploaded_file):
    """Reads the Streamlit UploadedFile object into a Pandas DataFrame."""
    try:
        bytes_data = uploaded_file.getvalue()
        df = pd.read_excel(BytesIO(bytes_data), sheet_name=0)
        
        # 1. Validate and Rename Columns
        required_cols = list(COLUMN_MAPPING.keys())
        if not all(col in df.columns for col in required_cols):
            missing = [col for col in required_cols if col not in df.columns]
            st.error(f"File validation failed. Missing required columns: **{', '.join(missing)}**.")
            st.info(f"Your Excel file must contain these exact column headers: **{', '.join(required_cols)}**.")
            return None

        df.rename(columns=COLUMN_MAPPING, inplace=True)
        
        # 2. Format Date Columns
        date_cols = ['expiry_date', 'service_expiry_date']
        for col in date_cols:
            df[col] = pd.to_datetime(df[col], errors='coerce').dt.strftime('%Y-%m-%d')
        
        return df
    
    except Exception as e:
        st.error(f"Error reading or processing the file: {e}")
        return None


def generate_llm_prompt(contract_data_json):
    """Creates a structured prompt for the LLM."""
    
    today = datetime.now().strftime('%Y-%m-%d')
    alert_end_date = (datetime.now() + timedelta(days=ALERT_DAYS_THRESHOLD)).strftime('%Y-%m-%d')
    
    system_prompt = f"""
    You are an expert Contract Analyst. Your task is to analyze the provided list of contracts in JSON format.
    The primary date for analysis is 'expiry_date' (Warranty Expiry).
    
    Identify all contracts where the **'expiry_date'** is between today ({today}) and {alert_end_date} (within {ALERT_DAYS_THRESHOLD} days).

    For each expiring contract found based on the 'expiry_date', extract and return the exact 'name', 'company', 'expiry_date', and the **'service_expiry_date'**. 
    
    Your final output MUST be a clean JSON array of objects, with NO surrounding text, explanation, or markdown formatting (e.g., no ```json).
    The required JSON schema is:
    [
        {{"name": "...", "company": "...", "expiry_date": "YYYY-MM-DD", "service_expiry_date": "YYYY-MM-DD"}},
        ...
    ]
    If no contracts are expiring in the window, return an empty array: [].
    """
    user_message = f"Analyze the following contract data (JSON):\n\n{contract_data_json}"
    return system_prompt, user_message


def analyze_contracts_with_bedrock(df, client):
    """Sends data to Bedrock and parses the structured response."""
    if df.empty:
        return []

    contract_data_json = df.to_json(orient='records', date_format='iso')
    system_prompt, user_message = generate_llm_prompt(contract_data_json)
    
    llm_output_text = "ERROR: Bedrock call failed before output could be received."

    try:
        response = client.converse(
            modelId=BEDROCK_MODEL_ID,
            messages=[
                {"role": "user", "content": [{"text": user_message}]}
            ],
            system=[{"text": system_prompt}],
            inferenceConfig={"temperature": 0.0, "maxTokens": 4096}
        )
        
        llm_output_text = response['output']['message']['content'][0]['text']
        
        # Robust cleanup for LLM markdown formatting
        llm_output_text = llm_output_text.strip()
        if llm_output_text.startswith("```"):
            start = llm_output_text.find('[')
            end = llm_output_text.rfind(']')
            if start != -1 and end != -1:
                llm_output_text = llm_output_text[start:end+1]
            else: 
                llm_output_text = llm_output_text.replace("```json", "").replace("```", "")
        
        return json.loads(llm_output_text)
        
    except Exception as e:
        st.error(f"LLM Processing Error: Could not get or parse response from Bedrock. Details: {e}")
        st.code(f"LLM Raw Output (Debug):\n{llm_output_text}", language="json")
        return []


# =========================================================================
# 3. STREAMLIT UI CONTENT
# =========================================================================

st.title("🧠 LLM-Powered Warranty & Maintenance Tracker")
st.markdown("Upload your asset ledger to automatically identify items where **Warranty Expiry** is approaching within the next **{}** days using Amazon Bedrock.".format(ALERT_DAYS_THRESHOLD))

st.divider()

# --- File Uploader and Process Button ---
uploaded_file = st.file_uploader(
    "Upload Excel Asset File (.xlsx)",
    type=['xlsx'],
    help="The file must contain columns: 'Customer Name', 'Product', 'Warranty Expiry', and 'Maintenance Expiry'."
)

if uploaded_file is not None:
    st.success(f"File **{uploaded_file.name}** uploaded successfully.")
    
    raw_df = read_uploaded_file(uploaded_file)

    if raw_df is not None:
        st.subheader("1. Preview of Uploaded Data")
        st.dataframe(raw_df.rename(columns={'expiry_date': 'Warranty Expiry (Primary)', 'service_expiry_date': 'Maintenance Expiry'}), use_container_width=True)

        if st.button("🚀 Analyze Assets with Amazon Bedrock", type="primary"):
            with st.spinner("Analyzing data with Bedrock... This may take a moment."):
                expiring_contracts = analyze_contracts_with_bedrock(raw_df, bedrock_client)
            
            st.divider()
            st.subheader("2. Expiring Assets Found (Based on Warranty Expiry)")

            if expiring_contracts:
                results_df = pd.DataFrame(expiring_contracts)
                
                # Rename the output columns for display
                results_df.rename(
                    columns={'company': 'Customer Name', 'name': 'Product', 
                             'expiry_date': 'Warranty Expiry', 
                             'service_expiry_date': 'Maintenance Expiry'}, 
                    inplace=True
                )
                
                # Highlight the Warranty Expiry column
                def highlight_expiry(s):
                    return ['background-color: #ffcccc' if col == 'Warranty Expiry' else '' for col in s.index]
                    
                st.dataframe(
                    results_df.style.apply(highlight_expiry, axis=0), 
                    use_container_width=True,
                    height=300
                )
                
                st.balloons()
                st.success(f"**Success!** {len(expiring_contracts)} asset(s) have an approaching **Warranty Expiry** date.")

            else:
                st.info("🎉 No assets are set to expire within the **{}** day threshold. All clear!".format(ALERT_DAYS_THRESHOLD))
                
# --- Footer ---
st.caption(" Credits to ALPHA GENES")