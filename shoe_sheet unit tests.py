# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.14.4
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Test shoe_sheet

# %%
import unittest
import importlib
import logging
import sys
import pandas as pd
import re

sys.path.append("../googledocs")
import shoe_sheet
import gdriveFile as gf

logger = logging.getLogger()
logging.basicConfig(level=logging.INFO,  # DEBUG, INFO, CRITICAL + 1
                    encoding="UTF-8",
                    force=True)

FIRST_TEST = re.compile(r"_00_")
TEST_SHEET = 'Copy of Shoes'  # edit the sheet and in the 'Shoes' tab pull down, make a copy!

def setup(idString):
    '''
    TestCase.setup() is called with a new object at the start of each
    test. So in this delegated piece, I cache the gdoc and sheet
    '''
    global cache_gdoc, cache_gdf
    mo = FIRST_TEST.search(idString)
    print(f"Test id: >{idString}< match? {mo}")
    if mo:  # first test of run
    
        importlib.reload(shoe_sheet)
    
        nameQuery = "running log"
        searchString = "name contains '{}'".format(nameQuery)

        # print('searching for "{}"'.format(searchString))

        access = gf.gdriveAccess()
        gdoc = gf.gdriveFile.findDriveFile(access, searchString)

        #logger.info(gdoc.showFileInfo())

        gdf = gdoc.toDataFrame(usecols=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9])
        cache_gdoc = gdoc
        cache_gdf = gdf
        return gdoc, gdf
    else:
        return cache_gdoc, cache_gdf


# %%
class TestStuff(unittest.TestCase):
    def setUp(self):
        self.gdoc, self.sheets = setup(self.id())
        pass

    def test_00_(self):
        shoes = shoe_sheet.ShoeManager(self.sheets[TEST_SHEET], handle=self.gdoc)
        shoes.show_sheet()
        self.assertEqual(shoes.backing_sheet.iloc[0,2],'StolenKoa')
        
    def test_01_(self):
        shoes = shoe_sheet.ShoeManager(self.sheets[TEST_SHEET], handle=self.gdoc)
        runner = shoe_sheet.ShoeTracker(shoes, year=2023)
        print(runner.base_shoes())
        #logger.info(runner.new_shoe_info)
        selected_data = self.sheets['2023']
        selected_data.index = pd.to_datetime(selected_data.iloc[:, 0], dayfirst=True)
        print(selected_data.iloc[[24]])  # note double [] returns dataframe not series
        assigned_shoe = selected_data.iloc[[24]].apply(runner.assign_names, axis='columns')
        print(list(assigned_shoe))
        self.assertEqual(assigned_shoe[0], 'ASICS-GT1000-8')
        
    def test_02(self):
        '''
        Test loading and writing back the shoe totals
        '''
        shoes = shoe_sheet.ShoeManager(self.sheets[TEST_SHEET], handle=self.gdoc)
        adder = shoe_sheet.ShoeMileYears(shoes, 6)
        adder.load()
        display(adder.year_hashes)
        self.assertEqual(adder.year_hashes[8][2022], 0)  # because new in 2023
        adder.total('2023Inov8 X-Talon', 2023, 200) # pretend 200 done in 2023
        self.assertEqual(adder.year_hashes[8][2023], 200)
        display(adder.shoe_manager.backing_sheet)
        adder.push_updates()

    def test_03_(self):
        '''
        Test that there can be 2 new shoes in a year
        '''
        shoes = shoe_sheet.ShoeManager(self.sheets[TEST_SHEET], handle=self.gdoc)
        runner = shoe_sheet.ShoeTracker(shoes, year=2023)
        print(runner.base_shoes())
        #logger.info(runner.new_shoe_info)
        selected_data = self.sheets['2023']
        selected_data.index = pd.to_datetime(selected_data.iloc[:, 0], dayfirst=True)
        for row in ([193, 191]):
            print(selected_data.iloc[[row]])  # note double [] returns dataframe not series
            assigned_shoe = selected_data.iloc[[row]].apply(runner.assign_names, axis='columns')
            print(list(assigned_shoe))
            # self.assertEqual(assigned_shoe[0], 'ASICS-GT1000-8')
        

def doTests():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestStuff)
    unittest.TextTestRunner(verbosity=2).run(suite)

doTests()

# %%
