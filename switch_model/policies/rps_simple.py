# Copyright 2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2, which is in the LICENSE file.

import os
from pyomo.environ import *

"""

This module defines a simple Renewable Portfolio Standard (RPS) policy scheme
for the Switch-Pyomo model. In this scheme, each fuel is categorized as RPS-
elegible or not. All non-fuel energy sources are assumed to be RPS-elegible.
Dispatched electricity that is generated by RPS-elegible sources in each
period is summed up and must meet an energy goal, set as a required percentage
of all energy that is generated in that period.

This module assumes that the generators.core.no_commit module is being used.
An error will be raised if this module is loaded along the
generators.core.commit package.

TODO:
Allow the usage of the commit module.

"""

def define_components(mod):
    """

    f_rps_eligible[f in FUELS] is a binary parameter that flags each fuel as
    elegible for RPS accounting or not.

    RPS_ENERGY_SOURCES is a set enumerating all energy sources that contribute
    to RPS accounting. It is built by union of all fuels that are RPS elegible
    and the NON_FUEL_ENERGY_SOURCES set.

    RPS_PERIODS is a subset of PERIODS for which RPS goals are defined.

    rps_target[p in RPS_PERIODS] is the fraction of total generated energy in
    a period that has to be provided by RPS-elegible sources.

    RPSProjFuelPower[g, t in FUEL_BASED_GEN_TPS] is an
    expression summarizing the power generated by RPS-elegible fuels in every
    fuel-based project. This cannot be simply taken to be equal to the
    dispatch level of the project, since a mix of RPS-elegible and unelegible
    fuels may be being consumed to produce that power. This expression is only
    valid when unit commitment is being ignored.

    RPSFuelEnergy[p] is an expression that sums all the energy produced using
    RPS-elegible fuels in fuel-based projects in a given period.

    RPSNonFuelEnergy[p] is an expression that sums all the energy produced
    using non-fuel sources in a given period.

    TotalGenerationInPeriod[p] is an expression that sums all the energy
    produced in a given period by all projects. This has to be calculated and
    cannot be taken to be equal to the total load in the period, because
    transmission losses could exist.

    RPS_Enforce_Target[p] is the constraint that forces energy produced by
    renewable sources to meet a fraction of the total energy produced in the
    period.

    """

    mod.f_rps_eligible = Param(
        mod.FUELS,
        within=Boolean,
        default=False)
    mod.RPS_ENERGY_SOURCES = Set(
        initialize=lambda m: set(m.NON_FUEL_ENERGY_SOURCES) | \
            set(f for f in m.FUELS if m.f_rps_eligible[f]))

    mod.RPS_PERIODS = Set(
        validate=lambda m, p: p in m.PERIODS)
    mod.rps_target = Param(
        mod.RPS_PERIODS,
        within=PercentFraction)

    mod.RPSFuelEnergy = Expression(
        mod.RPS_PERIODS,
        rule=lambda m, p: sum(
            m.tp_weight[t] *
            sum(
                m.GenFuelUseRate[g, t, f]
                for f in m.FUELS_FOR_GEN[g]
                if m.f_rps_eligible[f]
            ) / m.gen_full_load_heat_rate[g]
            for g in m.FUEL_BASED_GENS
            for t in m.TPS_FOR_GEN_IN_PERIOD[g, p])
        )
    mod.RPSNonFuelEnergy = Expression(
        mod.RPS_PERIODS,
        rule=lambda m, p: sum(m.DispatchGen[g, t] * m.tp_weight[t]
            for g in m.NON_FUEL_BASED_GENS
                for t in m.TPS_FOR_GEN_IN_PERIOD[g, p]))

    mod.RPS_Enforce_Target = Constraint(
        mod.RPS_PERIODS,
        rule=lambda m, p: (m.RPSFuelEnergy[p] + m.RPSNonFuelEnergy[p] >=
            m.rps_target[p] * total_demand_in_period(m, p)))


def total_generation_in_period(model, period):
    return sum(
        model.DispatchGen[g, t] * model.tp_weight[t]
        for g in model.GENERATION_PROJECTS
            for t in model.TPS_FOR_GEN_IN_PERIOD[g, period])


def total_demand_in_period(model, period):
    return sum(model.zone_total_demand_in_period_mwh[zone, period]
               for zone in model.LOAD_ZONES)


def load_inputs(mod, switch_data, inputs_dir):
    """
    The RPS target goals input file is mandatory, to discourage people from
    loading the module if it is not going to be used. It is not necessary to
    specify targets for all periods.

    Mandatory input files:
        rps_targets.tab
            PERIOD, rps_target

    The optional parameter to define fuels as RPS eligible can be inputted
    in the following file:
        fuels.tab
            fuel, f_rps_eligible

    """

    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'fuels.tab'),
        select=('fuel','f_rps_eligible'),
        optional_params=['f_rps_eligible'],
        param=(mod.f_rps_eligible,))
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, 'rps_targets.tab'),
        autoselect=True,
        index=mod.RPS_PERIODS,
        param=(mod.rps_target,))


def post_solve(instance, outdir):
    """
    Export energy statistics relevant to RPS studies.

    """

    import switch_model.reporting as reporting
    def get_row(m, p):
        row = (p,)
        row += (m.RPSFuelEnergy[p] / 1000,)
        row += (m.RPSNonFuelEnergy[p] / 1000,)
        row += (total_generation_in_period(m,p) / 1000,)
        row += ((m.RPSFuelEnergy[p] + m.RPSNonFuelEnergy[p]) /
            total_generation_in_period(m,p),)
        row += (total_demand_in_period(m, p),)
        row += ((m.RPSFuelEnergy[p] + m.RPSNonFuelEnergy[p]) /
            total_demand_in_period(m, p),)
        return row
    reporting.write_table(
        instance, instance.RPS_PERIODS,
        output_file=os.path.join(outdir, "rps_energy.txt"),
        headings=("PERIOD", "RPSFuelEnergyGWh", "RPSNonFuelEnergyGWh",
            "TotalGenerationInPeriodGWh", "RPSGenFraction",
            "TotalSalesInPeriodGWh", "RPSSalesFraction"),
        values=get_row)
