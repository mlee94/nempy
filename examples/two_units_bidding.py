import pandas as pd
from nempy import markets

# Volume of each bid, number of bands must equal number of bands in price_bids.
volume_bids = pd.DataFrame({
    'unit': ['A', 'B'],
    '1': [20, 50],  # MW
    '2': [20, 30],  # MW
    '3': [5, 10]  # More bid bands could be added.
})

# Price of each bid, bids must be monotonically increasing.
price_bids = pd.DataFrame({
    'unit': ['A', 'B'],
    '1': [50, 50],  # $/MW
    '2': [60, 55],  # $/MW
    '3': [100, 80]  # . . .
})

# Other unit properties
unit_info = pd.DataFrame({
    'unit': ['A', 'B'],
    'region': ['NSW', 'NSW'],  # MW
})

# The demand in the region\s being dispatched
demand = pd.DataFrame({
    'region': ['NSW'],
    'demand': [120]  # MW
})

# Create the market model
simple_market = markets.RealTime(unit_info=unit_info)
simple_market.set_unit_energy_volume_bids(volume_bids)
simple_market.set_unit_energy_price_bids(price_bids)
simple_market.set_demand_constraints(demand)

# Calculate dispatch and pricing
simple_market.dispatch()

# Return the total dispatch of each unit in MW.
simple_market.get_energy_dispatch()

# Return the price of energy in each region.
print(simple_market.get_energy_prices())
