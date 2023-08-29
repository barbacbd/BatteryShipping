from logging import getLogger, DEBUG
import requests
from io import BytesIO
from flask import Flask, request, send_file
from .package_data import PackagingSystem, LocationInformation, DateInformation
from json import loads, dumps
import pandas as pd
from os.path import exists, dirname, abspath, join

# always run in debugging mode since this is a simple test application
log = getLogger()
log.setLevel(DEBUG)

SIM_FILE = join(dirname(abspath(__file__)), "simulation.json")
DEC_FILE = join(dirname(abspath(__file__)), "declarations.json")



# could combine these into another function, leaving for now ...
if not exists(SIM_FILE):
    log.error(f"Failed to find: {SIM_FILE}")
    exit(1)
    
if not exists(DEC_FILE):
    log.error(f"Failed to find: {DEC_FILE}")
    exit(1)
    
with open(SIM_FILE) as json_file:
    json_data = loads(json_file.read())

with open(DEC_FILE) as json_file:
    dec_data = loads(json_file.read())
    
psystem = PackagingSystem(json_data=dec_data)
psystem._add_simulated_data(json_data=json_data)

app = Flask("battery_pickup")


@app.route('/info', methods=['GET', 'POST'])
def handle_info_request():
    """Handle the info request to find information about orders and
    return the order information to the user. All requests should be 
    supplied as JSON.
        
    The following values are accepted:
    state
    city
    street_address
    zip_code
    day
    month
    year
    order_id
    
    Operations:
    pickup-location: Return all future pick ups from this location.
    pickup-location & date: Return all orders that match both.
    order-id: Return the specific order information.
    """
    if request.is_json:
        json = request.json
            
        # easy-case: only a single order will match (at most)
        if "order_id" in json: 
            # search for the order ID. If this does not exist return an error
            orders = psystem.find_orders(order_id=json.get("order_id"))
        else:
            args = {}
            # order_id wasn't provided so the location or location and date must be provided
            date_data = {di: json.get(di, None) for di in ["day", "month", "year"]}
            if None in list(date_data.values()):
                log.debug("handle_info_request: day month year not provided correctly, skipping")
                date_data.clear()
            else:
                d = DateInformation()
                d.from_dict(date_data)
                args["date"] = d
                
            lookup_info = {
                li: json.get(li, None) 
                for li in ["state", "city", "street_address", "zip_code"]
            }
            if None in list(lookup_info.values()):
                log.error("handle_info_request: address information malformed")
                return "ERROR: please provide: state, city, street_address, zip_code", 400
            l = LocationInformation()
            l.from_dict(lookup_info)
            args["location"] = l
            
            orders = psystem.find_orders(**args)

        return dumps({"orders": [o.simple_json for o in orders if o]}, indent=2)

    return handle_info_request.__doc__, 400
    

@app.route('/quote', methods=['GET', 'POST'])
def handle_quote_request():
    """Handle the quote request to retrieve quote information for an order. when only
    the order_id is provided. If the user provides accept, the boolean value will be
    used to accept or deny a quote.
            
    The following values are accepted:
    order_id
    accept: boolean
    """
            
    if request.is_json:
        json = request.json
        
        if "order_id" in json and "accept" not in json: 
            # return a quote as a file to the user
            df = psystem.quote(json['order_id'])
            if df is None:
                return f"failed to create quote for order {json['order_id']}", 400

            #create an output stream
            output = BytesIO()
            writer = pd.ExcelWriter(output, engine='xlsxwriter')
                
            df.to_excel(writer, startrow = 0, merge_cells = False, sheet_name = "Sheet_1")
            workbook = writer.book
            worksheet = writer.sheets["Sheet_1"]
            format = workbook.add_format()
            format.set_bg_color('#eeeeee')
            worksheet.set_column(0,9,28)
            
            writer.close()
            output.seek(0)
        
            return send_file(
                output, 
                download_name=f"order_{json['order_id']}_quote.xlsx", 
                as_attachment=True
            )

        elif "order_id" in json and "accept" in json:
            answer = json["accept"]
            return_code = 200
            return_msg = f"Order ID: {json['order_id']} set to {bool(answer)}"
        
            if not isinstance(answer, bool):
                return_msg = "answer was not true/false, using false"
                return_code = 400
                answer = False

            psystem.quote_reply(
                json["order_id"], answer
            )

            return return_msg, return_code

    return handle_quote_request.__doc__
