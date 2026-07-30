"""
ULTRA MINIMAL - Test Claude API directly
No PDF parsing - just pure API test
"""
import streamlit as st
from anthropic import Anthropic

st.set_page_config(page_title="BMS Tool", layout="wide")

st.title("🏢 BMS Estimation Tool - Direct API Test")

# Sidebar settings
st.sidebar.title("Settings")
api_key = st.sidebar.text_input("Anthropic API Key", type="password")

if not api_key:
    st.warning("Enter API key to continue")
    st.stop()

st.success("✅ API Key received")

# Test section
st.subheader("Step 1: Test Claude API Directly")

test_text = """
Building: 175 Park Avenue
Systems: 5 ASHP units, 1 chiller, 2 DOAS, 1 AHU, ERU
Estimated I/O: 87 points
Integration: BACnet + Hardwired
"""

if st.button("🧪 Call Claude API"):
    try:
        st.write("Calling Claude API...")
        
        client = Anthropic(api_key=api_key)
        
        message = client.messages.create(
            model="claude-opus-5",
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": f"Analyze this BMS project briefly:\n{test_text}"
            }]
        )
        
        st.success("✅ SUCCESS!")
        st.write(message.content[0].text)
        
    except Exception as e:
        st.error(f"❌ Error: {type(e).__name__}")
        st.write(f"Details: {str(e)}")
        
        # Help
        if "not_found" in str(e).lower():
            st.info("💡 Model name issue - try 'claude-sonnet-5' instead")
        elif "auth" in str(e).lower():
            st.info("💡 API key issue")
        elif "timeout" in str(e).lower():
            st.info("💡 Network timeout - try again")
