from logging import getLogger, DEBUG
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from datetime import datetime
import pandas as pd


log = getLogger()
log.setLevel(DEBUG)


class BaseData:

    def from_dict(self, data):
        for k, v in data.items():
            if k in self.__slots__:
                setattr(self, k, v)

    @property
    def json(self):
        return {
            k: getattr(self, k) for k in self.__slots__
        }

    def __eq__(self, other):
        for slot in self.__slots__:
            if getattr(self, slot, None) is None or \
                getattr(other, slot, None) is None or \
                getattr(self, slot) != getattr(other, slot):
                return False
        return True

    def __ne__(self, other):
        return not self.__eq__(other)


class LocationInformation(BaseData):
    __slots__ = [
        "state",
        "city",
        "street_address",
        "zip_code"
    ]

class DateInformation(BaseData):
    # Could use a DateTime object
    __slots__ = ['day', 'month', 'year']

    def __ge__(self, other):
        return datetime(self.year, self.month, self.day) >= datetime(other.year, other.month, other.day)

class BatteryPackage(BaseData):

    __slots__ = [
        "battery_type",
        "battery_weight",
        "quality", # int 0 - 100%
        "return_reason",
    ]


class Order:
    
    def __init__(self, order_id=None, location=None, date=None, packages=[]):
        self.order_id = order_id
        self.distance_to_ship = 0.0

        self.location = None    
        if isinstance(location, LocationInformation):
            self.location = location
    
        self.date = None
        if isinstance(date, DateInformation):
            self.date = date

        self.packages = []
        for package in packages:
            if isinstance(package, BatteryPackage):
                self.packages.append(package)

        # quote is associated with an order. Only a single valid quote
        # can be associated with an order. 
        self.total_cost = None
        self.accepted = False
        self.df = None
        
    
    def from_dict(self, data):
        if "order_id" in data:
            self.order_id = data["order_id"]

        if "distance" in data:
            self.distance_to_ship = data["distance"]

        if "location" in data:
            l = LocationInformation()
            l.from_dict(data["location"])
            self.location = l

        if "date" in data:
            d = DateInformation()
            d.from_dict(data["date"])
            self.date = d
        
        if "packages" in data:
            for package in data["packages"]:
                p = BatteryPackage()
                p.from_dict(package)
                self.packages.append(p)
    
    @property
    def json(self):
        return {
            "order_id": self.order_id,
            "date": self.date.json,
            "location": self.location.json,
            "packages": [x.json for x in self.packages],
            "distance": self.distance_to_ship,
            "accepted": self.accepted
        }

    @property
    def simple_json(self):
        return {
            "order_id": self.order_id,
            "date": self.date.json,
            "location": self.location.json,
            "accepted": self.accepted
        }


def _simple_compare(x, y, var):
    if x == getattr(y, var):
        return y
    return None

def _find_inner_data(func, compare_var, list_vars, var):
    """Internal function to parallelize comparisons between types.
    This is a semi-generic function used for  the posibility of a large list
    of data.
    """
    matching_results = []

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(func, compare_var, list_vars[i], var): 
            i for i in range(len(list_vars))
        }

        for futr in as_completed(futures):
            if futr.result() is not None:
                matching_results.append(futr.result())
    
    return matching_results



class PackagingSystem:

    # Keys that are used for the JSON data that ultimately controls
    # the system.
    _required_data = [
        "qualities",      # quality of battery 0-100%
        "package_types",  # soft vs hard packaging materials
        "battery_packaging", 
        "weights",
        "battery_base_value",
        "distance",       # number of miles the package will travel
        "bonus" 
    ]

    def __init__(self, json_data={}):
        
        for key in PackagingSystem._required_data:
            if key not in json_data:
                raise KeyError(f"failed to find {key} in json configuration")
            setattr(self, key, json_data[key])
    
        self._order_lock = Lock()

        # dictionary of orders where the key is the order_id and the 
        # values are the order objects
        self.orders = {}

    def _add_simulated_data(self, json_data):
        """INTERNAL ONLY

        Add simulated data read in from a json file. This will fill the 
        Packaging system with data used for testing purposes only.
        """
        log.warn("PackagingSystem._add_simulated_data: invoking simulated data")
        if "orders" in json_data:
            for order in json_data["orders"]:
                o = Order()
                o.from_dict(order)

                if o.order_id is not None:
                    self.orders[o.order_id] = o
                else:
                    log.warn("PackagingSystem._add_simulated_data: order found without an id")


    def add_order(self, order):
        # If the order does not exist, add the order to the dictionary
        if order.order_id in self.orders:
            log.warn(f"PackagingSystem.add_order: {order.order_id} already exists, skipping")
            return
        
        log.debug(f"PackagingSystem.add_order: adding {order.order_id}")
        self.orders[order.order_id] = order
        
    def find_orders(self, order_id=None, location=None, date=None):
        """Find a list of orders that match the criteria. If the order_id is provided,
        at most one order will be returned in the list. If only the location is provided, then
        all orders with dates now-future will be returned. If the location and date are 
        provided then all orders from that date and location will be returned. 

        :param order_id [optional]: ID of the order
        :param location [optional]: LocationInformation
        :param date [optional]: DateInformation
        """
        if order_id is not None:
            # if the order_id is provided then we assume this is what
            # exactly what was meant to be retrieved. Even with errors,
            # don't default to using other data such as date and location
            return [self.orders.get(order_id, None)]
        
        if location is None:
            log.error("PackagingSystem.find_orders: a valid order id or location is required")
            return None
        
        matching_results = []

        # this could potentially get large due too a high number of orders,
        # let's parallelize this a bit 
        with self._order_lock:
            orders = list(self.orders.values())

        # filter out all data where the location does not match
        matching_results = _find_inner_data(_simple_compare, location, orders, "location")
        if matching_results and date is not None:
            # filter out the data where the date does not match
            matching_results = _find_inner_data(_simple_compare, date, matching_results, "date")

        return matching_results
    
    def quote_reply(self, order_id, answer):
        with self._order_lock:
            if order_id in self.orders:
                self.orders[order_id].accepted = answer
    
    def quote(self, order_id):
        """
        total = (Base for each type * quality) - shipping costs

        Minimum value is $100 total
        """
        with self._order_lock:
            order = self.orders.get(order_id, None)

        if not order:
            return None
        
        if order.total_cost is not None:
            return order.total_cost

        battery_types = []  # append empty string at the end later
        battery_weights = []
        battery_values = []  # last value will be the total
        battery_qualities = []

        # calculate shipping costs
        distance = order.distance_to_ship
        distance_mult = 1
        for d in self.distance:
            if distance >= d["min_distance"]:
                distance_mult = d["multiplier"]

        base_shipping = distance * distance_mult

        total_weight = 0.0
        total_to_pay = 0.0
        for package in order.packages:
            quality_mult = 0
            for quality in self.qualities:
                if package.quality <= quality["max_percent"]:
                    quality_mult = quality["multiplier"]
            
            total_to_pay = total_to_pay + (
                self.battery_base_value[package.battery_type] * quality_mult
            )
            total_weight = total_weight + package.battery_weight

            # dataframe data
            battery_types.append(package.battery_type)
            battery_weights.append(package.battery_weight)
            battery_values.append(self.battery_base_value[package.battery_type] * quality_mult)
            battery_qualities.append(package.quality)
        
        weight_mult = 1.0
        for w in self.weights:
            if total_weight <= w["max_weight"]:
                weight_mult = w["multiplier"]
                break

        total_to_pay = total_to_pay - (base_shipping * weight_mult)

        bonus = 0.0
        for b in self.bonus:
            if len(order.packages) >= b["min_packages"]:
                bonus = b["percent"]
        
        total_to_pay = total_to_pay + (total_to_pay * (bonus / 100.00))
        total_to_pay = round(max([total_to_pay, 100.00]), 2)

        # correct dataframe data
        bonus_data = [""] * len(battery_types) 
        bonus_data.append(f"{bonus}%")
        shipping_data = [""] * len(battery_types) 
        shipping_data.append(base_shipping)
        totals = [""] * len(battery_types)
        totals.append(total_to_pay)

        battery_types.append("")
        battery_weights.append(sum(battery_weights))
        battery_qualities.append("")
        battery_values.append(sum(battery_values))

        df = pd.DataFrame(
            [
                battery_types, battery_weights, battery_qualities, 
                battery_values, bonus_data, shipping_data, totals
            ],
            index=[
                "Battery Type", "Weight", "Quality", "Assessed Value", "Bonus", "Shipping", "Total"
            ]
        )

        with self._order_lock:
            self.orders[order_id].total_cost = total_to_pay
            self.orders[order_id].df = df

        return df
