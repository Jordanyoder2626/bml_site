import json
from datetime import datetime as dt

import pandas as pd

from scripts.api.DataLoader import DataLoader
from scripts.home.playoff_scenarios import PlayoffScenarios
from scripts.utils.database import Database
from scripts.api.Settings import Params
from scripts.api.Teams import Teams
from scripts.home.standings import Standings
from scripts.utils import constants
import scripts.scenarios.scenarios as scenarios
from scripts.simulations import simulations
from scripts.efficiency.efficiencies import plot_efficiency


season = constants.SEASON
data = DataLoader(2018)
week = data.teams()
print(json.dumps(week, indent=4))


params = Params(data)
teams = Teams(data)
week = params.regular_season_end+1 if params.current_week > params.regular_season_end+1 else params.current_week
n_teams = len(teams.team_ids)