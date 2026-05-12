from scripts.utils.database import Database
from scripts.efficiency.efficiencies import plot_efficiency
from scripts.utils import constants


# ============================================================
# CONFIG
# ============================================================

season = 2023
week = 15   # or whatever week you want


# ============================================================
# LOAD EFFICIENCY DATA
# ============================================================

eff = Database(
    table='efficiency',
    season=season,
    week=week
).retrieve_data(how='season')


# ============================================================
# GENERATE EFFICIENCY PLOT
# ============================================================

eff_plot = plot_efficiency(
    season=season,
    week=week,
    x='actual_lineup_score',
    y='optimal_lineup_score',
    xlab='Difference From Optimal Points per Week',
    ylab='Optimal Points per Week',
    title=''
)


print("Efficiency plot generated.")