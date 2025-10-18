import os
import json
import gspread
from sp_api.api import Orders
from sp_api.base import Marketplaces

# --- CONFIGURATION (Loaded securely from AWS Lambda Environment Variables) ---
LWA_CLIENT_ID = os.environ.get('LWA_CLIENT_ID')
LWA_CLIENT_SECRET = os.environ.get('LWA_CLIENT_SECRET')
AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
AWS_SECRET_KEY = os.environ.get('AWS_SECRET_KEY')
GOOGLE_CREDENTIALS_JSON = os.environ.get('GOOGLE_CREDENTIALS_JSON')
GOOGLE_SHEET_KEY = os.environ.get('GOOGLE_SHEET_KEY')
AMAZON_MARKETPLACE = Marketplaces.IN # Marketplace for India

def lambda_handler(event, context):
    """
    This function is triggered by an Amazon EventBridge notification for a new order.
    It fetches order details from the SP-API and writes them to a Google Sheet.
    """
    print(f"Received event: {json.dumps(event)}")

    # --- 1. Extract Order ID from the Notification ---
    try:
        notification_payload = event.get('detail', {}).get('payload', {})
        order_id = notification_payload.get('orderId')
        if not order_id:
            raise KeyError("'orderId' not found in the notification payload.")
        print(f"Processing notification for Order ID: {order_id}")
    except (KeyError, AttributeError) as e:
        print(f"Error: Could not find orderId in notification payload. Details: {e}")
        return {'statusCode': 400, 'body': 'Invalid notification format'}

    # --- 2. Fetch Order Details from Amazon SP-API ---
    try:
        print("Connecting to Amazon SP-API...")
        orders_client = Orders(
            marketplace=AMAZON_MARKETPLACE,
            credentials=dict(
                lwa_app_id=LWA_CLIENT_ID,
                lwa_client_secret=LWA_CLIENT_SECRET,
                aws_access_key=AWS_ACCESS_KEY_ID,
                aws_secret_key=AWS_SECRET_KEY,
            )
        )
        # Directly fetches the specific order and its items
        order_details = orders_client.get_order(order_id).payload
        order_items_response = orders_client.get_order_items(order_id).payload
        items = order_items_response.get('OrderItems', [])
        print("Successfully fetched order details from SP-API.")
    except Exception as e:
        print(f"Error fetching data from SP-API: {e}")
        return {'statusCode': 500, 'body': f"Failed to fetch from SP-API: {e}"}

    # --- 3. Format Data into a Row for the Spreadsheet ---
    item_names = ", ".join([item.get('Title', 'N/A') for item in items])
    total_price = sum(float(item.get('ItemPrice', {}).get('Amount', 0)) for item in items)
    shipping_address = order_details.get('ShippingAddress', {})

    new_row = [
        order_details.get('PurchaseDate'), order_details.get('AmazonOrderId'),
        order_details.get('OrderType'), order_details.get('ShipmentServiceLevelCategory'),
        "N/A (PII Restricted)", shipping_address.get('Name'),
        item_names, shipping_address.get('City'),
        f"{shipping_address.get('StateOrRegion', '')} {shipping_address.get('PostalCode', '')}".strip(),
        order_details.get('LatestShipDate'), order_details.get('LatestDeliveryDate'),
        str(total_price)
    ]
    print(f"Formatted row for Google Sheets: {new_row}")

    # --- 4. Write Data to Google Sheets ---
    try:
        print("Connecting to Google Sheets API...")
        credentials_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
        gc = gspread.service_account_from_dict(credentials_dict)
        worksheet = gc.open_by_key(GOOGLE_SHEET_KEY).sheet1
        worksheet.append_row(new_row, value_input_option='USER_ENTERED')
        print(f"Successfully wrote Order ID {order_id} to Google Sheet.")
    except Exception as e:
        print(f"Error writing to Google Sheets: {e}")
        return {'statusCode': 500, 'body': f"Failed to write to Google Sheets: {e}"}

    # --- Success ---
    return {
        'statusCode': 200,
        'body': json.dumps(f'Successfully processed Order ID: {order_id}')
    }
