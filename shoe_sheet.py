"""
utility classes for working out which shoes were used for each run in the
running log spreadsheet and tracking mileage run in them
"""
import datetime
import logging
import re
import pandas as pd
import yaml

logger = logging.getLogger()
# logging.basicConfig(
#     level=logging.INFO,  # DEBUG, INFO, CRITICAL + 1
#     encoding="UTF-8",
#     force=True,
# )

TYPE = "Type"
STARTDATE = "Start Date"


class ShoeManager:
    """
    wraps the google sheet
    knows how to read and write to the sheet
    """

    def __init__(self, raw_sheet: pd.DataFrame, handle=None):
        self.backing_sheet = raw_sheet
        self.handle = handle

        # check that the column names we rely on are in the sheet
        assert list(raw_sheet.columns[:3]) == ["Start Date", "Type", "Name"]

        self.backing_sheet["Start Date"] = pd.to_datetime(
            self.backing_sheet["Start Date"], dayfirst=True
        )
        # these words might appear in the Remarks column of the log to indicate
        # a particular shoe was used
        self.shoe_keywords = self.backing_sheet["Name"].apply(self.findwords)

    def idx_to_name(self, idx):
        """
        convert an index into a shoe name
        """
        return self.backing_sheet.loc[idx]["Name"]

    def name_to_idx(self, name):
        """
        find the named shoe and return its index
        """
        return self.backing_sheet.set_index("Name").index.get_loc(name)

    def show_sheet(self):
        """
        show the backing sheet
        """
        display(self.backing_sheet)

    def update_totals(self):
        """
        write back the YTD column to the google sheet
        """
        self.write_column("YTD")

    def write_column(self, colname):
        """
        for the named column, find its position in the list of columns
        then write back the entire column in the DataFrame to the sheet
        """
        if self.handle is None:
            print(
                f"no gdoc handle in object," "\n pass handle= on ShoeManager creation"
            )
            raise ValueError

        col_pos = self.backing_sheet.columns.get_loc(colname) + 1

        self.handle.addData(
            col_pos,
            2,  # +1 for title row, +1 for base
            list(self.backing_sheet[colname].apply(str)),
            arrayRepresents="COLUMN",
            sheet="Shoes",
            #sheet="Copy of Shoes",
        )

    @staticmethod
    def findwords(x):
        """
        split the lowercase words on whitespace or comma
        remove null strings (filter(None, ...) removes False things)
        and remove any spurious words, like 'xc'
        """
        foundwords = set(filter(None, re.split(r"[\s,]+", x.lower())))
        return foundwords - {"xc"}


class ShoeMileYears:
    """
    know how to store and retrieve the previous years' mileage
    """

    def __init__(self, shoe_manager, colname):
        """
        the data sits in the named column of the ShoeManager backing sheet
        """
        self.cn = colname
        self.shoe_manager = shoe_manager
        self.year_hashes = [None for i in range(len(self.shoe_manager.backing_sheet))]

    def load(self):
        """
        pull the data out of the column
        """
        for i, row in self.shoe_manager.backing_sheet.iterrows():
            self.year_hashes[i] = yaml.full_load(row[self.cn])

    def save(self):
        """
        push the year_hashes back into the DataFrame
        """
        for i, year_hash in enumerate(self.year_hashes):
            self.shoe_manager.backing_sheet.loc[i, self.cn] = yaml.dump(year_hash)

        self.shoe_manager.write_column(self.cn)

    def residual(self, year: int, **kwargs):
        """
        the residual mileage is the total mileage for the shoe == row
        prior to this year
        """
        assert year > 2020
        if "shoename" in set(kwargs.keys()):
            row_num = self.shoe_manager.name_to_idx(kwargs["shoename"])
        if "row_num" in set(kwargs.keys()):
            row_num = kwargs["row_num"]

        assert row_num < len(self.year_hashes)
        shoe_sum = 0
        for k in sorted(self.year_hashes[row_num].keys()):
            if k < year:
                shoe_sum += self.year_hashes[row_num][k]
        return shoe_sum

    def total(self, shoename: str, year: int, yearsTotal: float) -> float:
        """
        write the year's Total into the hash for the given year.
        add it to the residual giving the YTD total
         - pop that in the right column
         - and return the total
        """
        assert year > 2020
        row_num = self.shoe_manager.name_to_idx(shoename)
        assert row_num < len(self.year_hashes)
        self.year_hashes[row_num][year] = float(yearsTotal)
        total = yearsTotal + self.residual(year, shoename=shoename)
        # avoid chained indexing of iloc[row_num]['YTD']
        ytdIndex = self.shoe_manager.backing_sheet.columns.get_loc('YTD')
        self.shoe_manager.backing_sheet.iloc[row_num, ytdIndex] = total
        return total

    def push_updates(self):
        """
        write the updated hashes back into the sheet,
        and tell the shoe manager to write back the 'YTD' column too
        """
        self.save()
        self.shoe_manager.update_totals()

class ShoeDict(dict):
    """
    sub-class a dictionary so that we can provide a __missing__ method
    when used in pd.map() and presented with an unknown key, it just returns that
    key
    """

    def __missing__(self, key):
        return key


class ShoeTracker:
    """
    performs the manipulations on shoes in the run tracking sheets
    :param shoe_manager - the sheet wrapper
    :param year (int), optional - the year we care about tracking
    """

    def __init__(self, shoe_manager, **kwargs):
        """will be this year, or the one specified with year="""
        self.shoes = shoe_manager
        self.backing_sheet = self.shoes.backing_sheet
        logger.debug(kwargs.keys())
        if "year" in set(kwargs.keys()):
            current_year = int(kwargs["year"])
        else:
            current_year = datetime.datetime.now().year
        logger.info(f"{current_year=}")
        self.current_year = current_year
        # invalidate the shoe info now that year has changed
        self.base_shoe_info = None
        self.new_shoe_info = None
        self.shoe_name_mapping = ShoeDict()
        self.base_shoes()
        self.new_shoes()

    def base_shoes(self):
        """
        return the base shoes for the current year
        the base shoe is the newest shoe in each category at the start of the year
        """
        if self.base_shoe_info is None:
            try:
                assert self.current_year is not None
            except AssertionError as err:
                print(f"try using .set_current_year(<year=int>) first")
                raise err
            end_of_last_year = pd.to_datetime(str(self.current_year - 1) + "-12-31")
            # find for each category, the row of the newest shoe at the end of last year
            rows = (
                self.backing_sheet[self.backing_sheet[STARTDATE] <= end_of_last_year]
                .groupby(TYPE)[STARTDATE]
                .idxmax()
            )
            # now pull out useful info for that row
            info = (
                self.backing_sheet.reset_index()
                .iloc[rows][["index", "Start Date", "Name", "Type"]]
                .to_dict(orient="records")
            )
            logger.debug(f"{info=}")
            self.base_shoe_info = {
                i[TYPE]: {j: i[j] for j in i.keys() if j != TYPE} for i in info
            }
            logger.info(f"{self.base_shoe_info=}")
            self.shoe_name_mapping = ShoeDict(
                {"base" + i[TYPE]: i["Name"] for i in info}
            )
            logger.info(f"{self.shoe_name_mapping=}")
        return self.base_shoe_info

    def new_shoes(self):
        """
        return any shoes which are new in the current year
        """
        if self.new_shoe_info is None:
            try:
                assert self.current_year is not None
            except AssertionError as err:
                print(f"try using .set_current_year(<year=int>) first")
                raise err
            end_of_this_year = pd.to_datetime(str(self.current_year) + "-12-31")
            rows = (
                self.backing_sheet[self.backing_sheet["Start Date"] <= end_of_this_year]
                .groupby("Type")["Start Date"]
                .idxmax()
            )
            info = (
                self.backing_sheet.reset_index()
                .iloc[rows][["index", "Start Date", "Name", "Type"]]
                .to_dict(orient="records")
            )
            self.new_shoe_info = {
                i["Type"]: {j: i[j] for j in i.keys() if j != "Type"} for i in info
            }
            logger.info(f"{self.new_shoe_info=}")
            self.shoe_name_mapping |= ShoeDict(
                {"new" + i["Type"]: i["Name"] for i in info}
            )
            logger.info(f"{self.shoe_name_mapping=}")
        return self.new_shoe_info

    def assign_names(self, row):
        """
        Two dicts, base, and newest are passed in: these contain
        the start dates for the base shoe and newest shoe in each
        category
        """

        logger.debug(f"{self=} {row=}")
        # find words in the 'Remarks' column and see whether one identifies a shoe
        remark_words = self.shoes.findwords(row["Remarks"])
        if bool(remark_words):  # not empty set
            logger.debug(f"{remark_words=}")
            for idx, val in self.shoes.shoe_keywords.iteritems():
                if bool(val.intersection(remark_words)):
                    logger.debug(f"<== assign from remarks {idx=}")
                    return self.shoes.backing_sheet.iloc[idx]["Name"]

        # if a Poole run, then use the old fixed shoe if it's after they went there
        route_words = self.shoes.findwords(row["Route"])
        if bool(route_words):  # not empty
            if row.name > pd.to_datetime("2021-08-02") and route_words.intersection(
                {"upton", "holes", "hamworthy", "baiter", "sandbanks"}
            ):
                logger.debug(f"<== assign from route {route_words=}")
                return self.shoes.backing_sheet.iloc[3]["Name"]

        matchobj = re.search(r"xc", row["Remarks"], flags=re.I)  # ignore case
        if matchobj:
            sup = "XC"
        else:
            sup = "Road"

        if (
            self.new_shoe_info[sup]["Start Date"]
            > self.base_shoe_info[sup]["Start Date"]
        ):  # there is a newer shoe this year
            if row.name < self.new_shoe_info[sup]["Start Date"]:
                logger.debug(f"<== assign before new {sup=}")
                return self.base_shoe_info[sup]["Name"]

            logger.debug(f"<== assign after new {sup=}")
            return self.new_shoe_info[sup]["Name"]

        logger.debug(f"<== assign from base {sup=}")
        return self.base_shoe_info[sup]["Name"]
