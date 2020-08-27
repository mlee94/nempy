import os
import sqlite3
import pandas as pd
from nempy import markets
from nempy.historical import historical_inputs_from_mms_db as hi

# Create a list of the historical dispatch intervals to be used.
dispatch_intervals = hi.datetime_dispatch_sequence(start_time='2020/01/02 00:00:00',
                                                   end_time='2020/01/02 00:05:00')

# Build a database of historical inputs if it doesn't already exist.
if not os.path.isfile('historical.db'):
    con = sqlite3.connect('historical.db')

    # Create a data base manager.
    inputs_manager = hi.DBManager(connection=con)

    # This is the first time the database has been used so we need to add the tables.
    # inputs_manager.create_tables()

    # Download the relevant historical data from http://nemweb.com.au/#mms-data-model and into the database.
    inputs_manager.DUDETAILSUMMARY.set_data(year=2020, month=1)  # Unit information
    inputs_manager.BIDPEROFFER_D.add_data(year=2020, month=1)  # historical volume bids
    inputs_manager.BIDDAYOFFER_D.add_data(year=2020, month=1)  # historical price bids
    inputs_manager.DISPATCHLOAD.add_data(year=2020, month=1)  # unit operating limits
    inputs_manager.DISPATCHREGIONSUM.add_data(year=2020, month=1)  # historical demand
    inputs_manager.INTERCONNECTOR.set_data(year=2020, month=1)  # Regions connected by interconnector
    inputs_manager.DISPATCHINTERCONNECTORRES.add_data(year=2020, month=1)  # Interconnectors in each dispatch interval
    inputs_manager.INTERCONNECTORCONSTRAINT.set_data(year=2020, month=1)  # Interconnector data
    inputs_manager.LOSSFACTORMODEL.set_data(year=2020, month=1)  # Regional demand coefficients in loss functions
    inputs_manager.LOSSMODEL.set_data(year=2020, month=1)  # Break points for linear interpolation of loss functions
    inputs_manager.SPDREGIONCONSTRAINT.set_data(year=2020, month=1)  # Link of FCAS requirements across regions.
    inputs_manager.GENCONDATA.set_data(year=2020, month=1)  # Constraint types
    inputs_manager.DISPATCHCONSTRAINT.add_data(year=2020, month=1)  # Constraints rhs.

    con.close()

# Connect to the database of historical inputs
con = sqlite3.connect('historical.db')
inputs_manager = hi.DBManager(connection=con)

# List for saving inputs to.
outputs = []

# Create and dispatch the spot market for each dispatch interval.
for interval in dispatch_intervals:
    # Transform the historical input data into the format accepted by the Spot market class.
    # Unit info.
    DUDETAILSUMMARY = inputs_manager.DUDETAILSUMMARY.get_data(interval)
    unit_info = hi.format_unit_info(DUDETAILSUMMARY)

    # Unit bids.
    BIDPEROFFER_D = inputs_manager.BIDPEROFFER_D.get_data(interval)
    BIDDAYOFFER_D = inputs_manager.BIDDAYOFFER_D.get_data(interval)

    # The unit operating conditions at the start of the historical interval.
    DISPATCHLOAD = inputs_manager.DISPATCHLOAD.get_data(interval)
    unit_limits = hi.determine_unit_limits(DISPATCHLOAD, BIDPEROFFER_D)

    # FCAS bid prepocessing
    BIDPEROFFER_D = hi.scaling_for_agc_enablement_limits(BIDPEROFFER_D, DISPATCHLOAD)
    BIDPEROFFER_D = hi.scaling_for_agc_ramp_rates(BIDPEROFFER_D, DISPATCHLOAD)
    BIDPEROFFER_D = hi.scaling_for_uigf(BIDPEROFFER_D, DISPATCHLOAD, DUDETAILSUMMARY)
    BIDPEROFFER_D, BIDDAYOFFER_D = hi.enforce_preconditions_for_enabling_fcas(
        BIDPEROFFER_D, BIDDAYOFFER_D, DISPATCHLOAD, unit_limits.loc[:, ['unit', 'capacity']])
    BIDPEROFFER_D, BIDDAYOFFER_D = hi.use_historical_actual_availability_to_filter_fcas_bids(
        BIDPEROFFER_D, BIDDAYOFFER_D, DISPATCHLOAD)

    # Change bidding data to conform to nempy input format.
    volume_bids = hi.format_volume_bids(BIDPEROFFER_D)
    price_bids = hi.format_price_bids(BIDDAYOFFER_D)
    fcas_trapeziums = hi.format_fcas_trapezium_constraints(BIDPEROFFER_D)

    # Demand on regional basis.
    DISPATCHREGIONSUM = inputs_manager.DISPATCHREGIONSUM.get_data(interval)
    regional_demand = hi.format_regional_demand(DISPATCHREGIONSUM)

    # FCAS volumes required.
    SPDREGIONCONSTRAINT = inputs_manager.SPDREGIONCONSTRAINT.get_data(interval)
    DISPATCHCONSTRAINT = inputs_manager.DISPATCHCONSTRAINT.get_data(interval)
    GENCONDATA = inputs_manager.GENCONDATA.get_data(interval)
    fcas_requirements = hi.format_fcas_market_requirements(SPDREGIONCONSTRAINT, DISPATCHCONSTRAINT, GENCONDATA)

    # Interconnector details.
    INTERCONNECTOR = inputs_manager.INTERCONNECTOR.get_data()
    INTERCONNECTORCONSTRAINT = inputs_manager.INTERCONNECTORCONSTRAINT.get_data(interval)
    interconnectors = hi.format_interconnector_definitions(INTERCONNECTOR,
                                                           INTERCONNECTORCONSTRAINT)
    interconnector_loss_coefficients = hi.format_interconnector_loss_coefficients(INTERCONNECTORCONSTRAINT)
    LOSSFACTORMODEL = inputs_manager.LOSSFACTORMODEL.get_data(interval)
    interconnector_demand_coefficients = hi.format_interconnector_loss_demand_coefficient(LOSSFACTORMODEL)
    LOSSMODEL = inputs_manager.LOSSMODEL.get_data(interval)
    interpolation_break_points = hi.format_interpolation_break_points(LOSSMODEL)
    loss_functions = hi.create_loss_functions(interconnector_loss_coefficients, interconnector_demand_coefficients,
                                              regional_demand.loc[:, ['region', 'loss_function_demand']])

    # Create a market instance.
    market = markets.SpotMarket()

    # Add generators to the market.
    market.set_unit_info(unit_info.loc[:, ['unit', 'region', 'dispatch_type']])

    # Set volume of each bids.
    volume_bids = volume_bids[volume_bids['unit'].isin(list(unit_info['unit']))]
    market.set_unit_volume_bids(volume_bids.loc[:, ['unit', 'service', '1', '2', '3', '4', '5',
                                                    '6', '7', '8', '9', '10']])

    # Set prices of each bid.
    price_bids = price_bids[price_bids['unit'].isin(list(unit_info['unit']))]
    price_bids = price_bids.loc[:, ['unit', 'service', '1', '2', '3', '4', '5',
                                    '6', '7', '8', '9', '10']]
    market.set_unit_price_bids(price_bids)

    # Set unit operating limits.
    market.set_unit_capacity_constraints(unit_limits.loc[:, ['unit', 'capacity']])
    market.set_unit_ramp_up_constraints(unit_limits.loc[:, ['unit', 'initial_output', 'ramp_up_rate']])
    market.set_unit_ramp_down_constraints(unit_limits.loc[:, ['unit', 'initial_output', 'ramp_down_rate']])

    # Create constraints that enforce the top of the FCAS trapezium.
    fcas_availability = fcas_trapeziums.loc[:, ['unit', 'service', 'max_availability']]
    market.set_fcas_max_availability(fcas_availability)

    # Create constraints the enforce the lower and upper slope of the FCAS regulation
    # service trapeziums.
    regulation_trapeziums = fcas_trapeziums[fcas_trapeziums['service'].isin(['raise_reg', 'lower_reg'])]
    market.set_energy_and_regulation_capacity_constraints(regulation_trapeziums)
    market.set_joint_ramping_constraints(regulation_trapeziums.loc[:, ['unit', 'service']],
                                         unit_limits.loc[:, ['unit', 'initial_output',
                                                             'ramp_down_rate', 'ramp_up_rate']])

    # Create constraints that enforce the lower and upper slope of the FCAS contingency
    # trapezium. These constrains also scale slopes of the trapezium to ensure the
    # co-dispatch of contingency and regulation services is technically feasible.
    contingency_trapeziums = fcas_trapeziums[~fcas_trapeziums['service'].isin(['raise_reg', 'lower_reg'])]
    market.set_joint_capacity_constraints(contingency_trapeziums)

    # Set regional demand.
    market.set_demand_constraints(regional_demand.loc[:, ['region', 'demand']])

    # Set FCAS requirements.
    market.set_fcas_requirements_constraints(fcas_requirements)

    # Create the interconnectors.
    market.set_interconnectors(interconnectors)

    # Create loss functions on per interconnector basis.
    market.set_interconnector_losses(loss_functions, interpolation_break_points)

    # Calculate dispatch.
    market.dispatch()

    print('Dispatch for interval {} complete.'.format(interval))

    # Save prices from this interval
    prices = market.get_energy_prices()
    prices['time'] = interval
    prices['service'] = 'energy'
    outputs.append(prices)
    prices = market.get_fcas_prices()
    prices['time'] = interval
    outputs.append(prices)

con.close()
print(pd.concat(outputs))
#    region      price                 time
# 0    NSW1  61.114147  2020/01/02 15:05:00
# 1    QLD1  58.130015  2020/01/02 15:05:00
# 2     SA1  72.675411  2020/01/02 15:05:00
# 3    TAS1  73.013327  2020/01/02 15:05:00
# 4    VIC1  68.778493  2020/01/02 15:05:00
# ..    ...        ...                  ...
# 0    NSW1  54.630861  2020/01/02 21:00:00
# 1    QLD1  55.885854  2020/01/02 21:00:00
# 2     SA1  53.038412  2020/01/02 21:00:00
# 3    TAS1  61.537939  2020/01/02 21:00:00
# 4    VIC1  57.040000  2020/01/02 21:00:00
#
# [360 rows x 3 columns]
