from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
import os
from openai import AzureOpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# === Config from .env ===
endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
model_name = os.getenv("AZURE_OPENAI_MODEL_NAME")
subscription_key = os.getenv("AZURE_OPENAI_KEY")
api_version = os.getenv("AZURE_OPENAI_API_VERSION")

TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
D365_ENV_URL = os.getenv("D365_ENV_URL")

# === FastAPI Setup ===
app = FastAPI()

# === Request and Response Models ===
class McpRequest(BaseModel):
    name: str
    context: str

class McpResponse(BaseModel):
    message: str
    processedContext: str

# === Azure AD Token for D365 F&O ===
def get_access_token() -> str:
    token_url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/token"
    payload = {
        'grant_type': 'client_credentials',
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'resource': D365_ENV_URL
    }

    response = requests.post(token_url, data=payload)
    if response.status_code == 200:
        return response.json().get('access_token')
    else:
        raise Exception(f"Token request failed: {response.status_code} - {response.text}")

# === Azure OpenAI Client ===
client = AzureOpenAI(
    api_version=api_version,
    azure_endpoint=endpoint,
    api_key=subscription_key,
)

# === Query Azure OpenAI for OData ===
def query_llm_for_odata(intent: str) -> str:
    response = client.chat.completions.create(
        model=deployment,  # This refers to your Azure deployment name
        messages=[
            {"role": "system", "content": "You generate valid OData query paths for Dynamics 365 Finance & Operations."
             "Return just the relative URL path after /data/ with no explanation or markdown."
             #"Example:CustTransactions$top=10&CurrencyCode ne 'USD'"
             "Example: CustomersV3?$top=10 "
             #"After you execute the OData query, you will return customer names and IDs. Return response as as it is from Odata in XML format"             
             },
            {"role": "user", "content": intent}
        ],
        temperature=0.2
    )
    return response.choices[0].message.content.strip()

# === Query Azure OpenAI for OData ===
def query_llm_for_changes(intent: str) -> str:
    response = client.chat.completions.create(
        model=deployment,  # This refers to your Azure deployment name
        messages=[
            {
                "role": "system", "content": "Return only customer names and CustomerAccount. return original OData response as it is in XML format."
                "Return with no explanation or markdown."             
             },
            {"role": "user", "content": intent}
        ],
        temperature=0.2
    )
    return response.choices[0].message.content.strip()

# === Call D365 F&O OData Endpoint ===
def call_odata(query_path: str) -> dict:
    base_url = f"{D365_ENV_URL}/data"
    full_url = f"{base_url}/{query_path}"

    headers = {
        "Authorization": f"Bearer {get_access_token()}",
        "Accept": "application/json"
    }
    print(f"Calling OData endpoint: {full_url}")
    response = requests.get(full_url, headers=headers)
    # Print raw response text (HTML or JSON)
    #print("=== RAW ODATA RESPONSE ===")
   # print(response.text)
   # print("==========================")
    return response.json() if response.status_code == 200 else {"error": response.text}

# === MCP Endpoint ===
@app.post("/api/mcp", response_model=McpResponse)
def process_mcp(request: McpRequest):
    if not request.name or not request.context:
        raise HTTPException(status_code=400, detail="Name and Context are required.")

    try:
        if "get customers" in request.context.lower():
            query = query_llm_for_odata(request.context)
            print(f"Generated OData query: {query}")
            results = call_odata(query)
            print("=== ODATA RESPONSE ===")
            print(results)
            print("==========================")
            print("Now Processing the OData response to get customer names and IDs")
            results = query_llm_for_changes(str(results))
            print("=== Data changes after OData ===")
            print(results)
            print("==========================")
            

            return McpResponse(
                message=f"Hello {request.name}, here are your custmers:",
                processedContext=str(results)
            )
        
        else:
            return McpResponse(
                message=f"Hello {request.name}, your context was processed.",
                processedContext=request.context.upper()
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
