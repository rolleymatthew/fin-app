from __future__ import annotations

from datetime import date as dt_date, datetime
from decimal import Decimal
from pydantic import BaseModel, Field, ConfigDict

# Generated from Java entity classes

class BaseDoc(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    def __getattr__(self, name: str):
        try:
            return super().__getattr__(name)
        except AttributeError:
            if not name.startswith('_'):
                return None
            raise

class AssetsBankEntity(BaseDoc):
    __collection__ = "assets_bank"
    id: str | None = Field(default=None, alias="_id")
    updatedAt: str | datetime | None = None

class AssetsInsuranceEntity(BaseDoc):
    __collection__ = "assets_insurance"
    id: str | None = Field(default=None, alias="_id")
    updatedAt: str | datetime | None = None

class AssetsSecuritiesEntity(BaseDoc):
    __collection__ = "assets_securities"
    id: str | None = Field(default=None, alias="_id")
    updatedAt: str | datetime | None = None

class AssetsUniversalEntity(BaseDoc):
    __collection__ = "assets_universal"
    id: str | None = Field(default=None, alias="_id")
    updatedAt: str | datetime | None = None

class BonusEntity(BaseDoc):
    __collection__ = "bonus"
    id: str | None = Field(default=None, alias="_id")
    updatedAt: str | datetime | None = None

class CashFlowBankEntity(BaseDoc):
    __collection__ = "cash_flow_bank"
    id: str | None = Field(default=None, alias="_id")
    updatedAt: str | datetime | None = None

class CashFlowInsuranceEntity(BaseDoc):
    __collection__ = "cash_flow_insurance"
    id: str | None = Field(default=None, alias="_id")
    updatedAt: str | datetime | None = None

class CashFlowSecuritiesEntity(BaseDoc):
    __collection__ = "cash_flow_securities"
    id: str | None = Field(default=None, alias="_id")
    updatedAt: str | datetime | None = None

class CashFlowUniversalEntity(BaseDoc):
    __collection__ = "cash_flow_universal"
    id: str | None = Field(default=None, alias="_id")
    updatedAt: str | datetime | None = None

class DuPondEntity(BaseDoc):
    __collection__ = "dupond"
    id: str | None = Field(default=None, alias="_id")
    updatedAt: str | datetime | None = None

class EtfEntity(BaseDoc):
    __collection__ = "etf"
    id: str | None = Field(default=None, alias="_id")
    statDate: str | None = None
    secName: str | None = None
    etfType: str | None = None
    secCode: int | None = None
    num: str | None = None
    totVol: Decimal | None = None
    addVol: int | None = None
    addAmount: int | None = None
    beforeDate: str | None = None
    beforeValue: Decimal | None = None
    addTotValue: int | None = None
    pinyin: str | None = None
    updatedAt: str | datetime | None = None


class EtfQuarterEntity(BaseDoc):
    """ETF 季度份额/规模数据（东方财富 gmbd 接口）"""
    __collection__ = "etf_quarter"
    id: str | None = Field(default=None, alias="_id")
    secCode: int | None = None
    secName: str | None = None
    statDate: str | None = None        # 季度末日期 YYYY-MM-DD
    totVol: Decimal | None = None       # 期末总份额（亿份）
    netAsset: Decimal | None = None     # 期末净资产（亿元）
    purchaseVol: Decimal | None = None  # 期间申购（亿份）
    redeemVol: Decimal | None = None    # 期间赎回（亿份）
    changeRate: str | None = None       # 净资产变动率（如 "-9.53%"）
    frequency: str | None = None        # 固定为 "quarter"
    source: str | None = None           # 固定为 "eastmoney_gmbd"
    updatedAt: str | datetime | None = None

class FinEntity(BaseDoc):
    __collection__ = "fin"
    id: str | None = Field(default=None, alias="_id")
    secCode: str | None = None
    updatedAt: str | datetime | None = None
    reportDate: str | None = None
    operatingIncome: float | None = None
    revenueGrowthRate: float | None = None
    netProfit: float | None = None
    netProfitGrowthRate: float | None = None
    operatingGrossProfitMargin: float | None = None
    netInterestRate: float | None = None
    operatingProfitMargin: float | None = None
    returnOnNetAssets: float | None = None
    netOperatingCashFlow: float | None = None
    lAndLiabRatioww: float | None = None

class KLineDataEntity(BaseDoc):
    __collection__ = None
    date: str | None = None
    open: str | None = None
    close: str | None = None
    higher: str | None = None
    lower: str | None = None
    vol: str | None = None
    amount: str | None = None
    amplitude: str | None = None
    amountOfIncrease: str | None = None
    UpDownAmount: str | None = None
    turnOver: str | None = None
    amountOfAverage: str | None = None

class KLineEntity(BaseDoc):
    __collection__ = "k_line"
    code: str | None = Field(default=None, alias="_id")
    name: str | None = None
    klines: list[KLineDataEntity] | None = None
    updatedAt: str | datetime | None = None

class ProfitBankEntity(BaseDoc):
    __collection__ = "profit_bank"
    id: str | None = Field(default=None, alias="_id")
    updatedAt: str | datetime | None = None

class ProfitSecuritiesEntity(BaseDoc):
    __collection__ = "profit_securities"
    id: str | None = Field(default=None, alias="_id")
    updatedAt: str | datetime | None = None

class ProfitForecastEntity(BaseDoc):
    __collection__ = "profit_forecast"
    secucode: str | None = None
    securityCode: str | None = Field(default=None, alias="_id")
    securityNameAbbr: str | None = None
    ratingOrgNum: int | None = None
    ratingBuyNum: int | None = None
    ratingAddNum: int | None = None
    ratingNeutralNum: Object | None = None
    ratingReduceNum: Object | None = None
    ratingSaleNum: Object | None = None
    year1: int | None = None
    yearMark1: str | None = None
    eps1: float | None = None
    year2: int | None = None
    yearMark2: str | None = None
    eps2: float | None = None
    year3: int | None = None
    yearMark3: str | None = None
    eps3: float | None = None
    year4: int | None = None
    yearMark4: str | None = None
    eps4: float | None = None
    industryBoard: str | None = None
    industryBoardSzm: str | None = None
    conceptindexBoard: str | None = None
    conceptindexBoardSzm: str | None = None
    regionBoard: str | None = None
    regionBoardSzm: str | None = None
    marketBoard: str | None = None
    decAimpricemax: int | None = None
    decAimpricemin: float | None = None
    ratingLongNum: int | None = None

class ProfitInsuranceEntity(BaseDoc):
    __collection__ = "profit_insurance"
    id: str | None = Field(default=None, alias="_id")
    updatedAt: str | datetime | None = None

class ProfitPercentEntity(BaseDoc):
    __collection__ = None
    securityCode: str | None = None
    securityName: str | None = None
    ReportData: str | None = None
    grossProfit: float | None = None
    operatProfit: float | None = None
    netProfit: float | None = None
    addGrossProfit: float | None = None
    addOperatProfit: float | None = None
    addNetProfit: float | None = None
    netAssetsWeight: str | None = None
    addNetAssetsWeight: str | None = None

class ProfitUniversalEntity(BaseDoc):
    __collection__ = "profit_universal"
    id: str | None = Field(default=None, alias="_id")
    updatedAt: str | datetime | None = None

class ScoreEntity(BaseDoc):
    __collection__ = "yb_score"
    id: str | None = Field(default=None, alias="_id")
    code: str | None = None
    name: str | None = None
    date: str | None = None
    score: int | None = None
    result: str | None = None
    grossProfitPer: float | None = None
    grossProfitScore: str | None = None
    operatProfitPer: float | None = None
    operatProfitScore: str | None = None
    netProfitPer: float | None = None
    netProfitScore: str | None = None
    netAssetsWeightPer: float | None = None
    netAssetsWeightScore: str | None = None
    liabilPer: float | None = None
    liabilScore: str | None = None
    assetsPer: float | None = None
    assetsScore: str | None = None
    stockPer: float | None = None
    stockScore: str | None = None
    accountsReceivablePer: float | None = None
    accountsReceivableScore: str | None = None
    netCashFlowFromOperatingActivities: float | None = None
    netCashFlowFromOperatingActivitiesScore: str | None = None
    netCashFlowFromInvestmentActivities: float | None = None
    netCashFlowFromInvestmentActivitiesScore: str | None = None
    netCashFlowFromFinancingActivities: float | None = None
    netCashFlowFromFinancingActivitiesScore: str | None = None

class SecCodeEntity(BaseDoc):
    __collection__ = "sec_code"
    id: str | None = Field(default=None, alias="_id")
    secucode: str | None = None
    securityCode: str | None = None
    securityNameAbbr: str | None = None
    orgName: str | None = None
    formername: str | None = None
    regionbk: str | None = None
    em2016: str | None = None
    blgainian: str | None = None
    regCapital: float | None = None
    totalNum: int | None = None
    tatolnumber: int | None = None
    securityCodeType: int | None = None
    securityTypeCode: str | None = None
    isInnovation: int | None = None
    securityPinyin: str | None = None
    listingDate: str | None = None
    tradeMarket: str | None = None
    tradeMarketCode: str | None = None
    securityInnerCode: str | None = None
    orgCode: str | None = None
    listingState: str | None = None
    securityType: str | None = None
    orgType: str | None = None
    codeType: str | None = None
    orgTypeCode: str | None = None
    currency: str | None = None
    accountFirm: str | None = None
    legalAdviser: str | None = None
    updatedAt: str | datetime | None = None

class ShareBonusEntity(BaseDoc):
    __collection__ = "share_bonus"
    id: str | None = Field(default=None, alias="_id")
    updatedAt: str | datetime | None = None

class CashFlowScoreEntity(BaseDoc):
    __collection__ = None
    date: str | None = None
    securityCode: str | None = None
    securityNameAbbr: str | None = None
    netCashFlowFromOperatingActivities: str | None = None
    netCashFlowFromInvestmentActivities: str | None = None
    netCashFlowFromFinancingActivities: str | None = None
    type: str | None = None
    properties: str | None = None

class YbRoeEntity(BaseDoc):
    __collection__ = None
    lastonequarterhigher: Decimal | None = None
    lastonequarteraverage: Decimal | None = None
    lastonequarterlower: Decimal | None = None
    lasttwoquarterhigher: Decimal | None = None
    lasttwoquarteraverage: Decimal | None = None
    lasttwoquarterlower: Decimal | None = None
    lastthreequarterhigher: Decimal | None = None
    lastthreequarteraverage: Decimal | None = None
    lastthreequarterlower: Decimal | None = None
    lastfourquarterhigher: Decimal | None = None
    lastfourquarteraverage: Decimal | None = None
    lastfourquarterlower: Decimal | None = None
    lastoneyearhigher: Decimal | None = None
    lastoneyearaverage: Decimal | None = None
    lastoneyearlower: Decimal | None = None
    lasttwoyearhigher: Decimal | None = None
    lasttwoyearaverage: Decimal | None = None
    lasttwoyearlower: Decimal | None = None
    lastthreeyearhigher: Decimal | None = None
    lastthreeyearaverage: Decimal | None = None
    lastthreeyearlower: Decimal | None = None
    lastfouryearhigher: Decimal | None = None
    lastfouryearaverage: Decimal | None = None
    lastfouryearlower: Decimal | None = None
    onequarterdate: str | None = None
    oneepstotal: Decimal | None = None
    oneepscurrent: Decimal | None = None
    twoquarterdate: str | None = None
    twoepstotal: Decimal | None = None
    twoepscurrent: Decimal | None = None
    threequarterdate: str | None = None
    threeepstotal: Decimal | None = None
    threeepscurrent: Decimal | None = None
    fourquarterdate: str | None = None
    fourepstotal: Decimal | None = None
    fourepscurrent: Decimal | None = None
    oneyeardate: str | None = None
    oneyearepstotal: Decimal | None = None
    twoyeardate: str | None = None
    twoyearepstotal: Decimal | None = None
    threeyeardate: str | None = None
    threeyearepstotal: Decimal | None = None
    fouryeardate: str | None = None
    fouryearepstotal: Decimal | None = None
    fouryearavarageepstotal: Decimal | None = None
    laterfirstqepstotal: Decimal | None = None
    latertwoqepstotal: Decimal | None = None
    laterthreeqepstotal: Decimal | None = None
    laterfourqepstotal: Decimal | None = None
    laterfourqavaepstotal: Decimal | None = None
    oneyearpedate: str | None = None
    oneyearpehigher: Decimal | None = None
    oneyearpeaverage: Decimal | None = None
    oneyearpelower: Decimal | None = None
    twoyearpedate: str | None = None
    twoyearpehigher: Decimal | None = None
    twoyearpeaverage: Decimal | None = None
    twoyearpelower: Decimal | None = None
    threeyearpedate: str | None = None
    threeyearpehigher: Decimal | None = None
    threeyearpeaverage: Decimal | None = None
    threeyearpelower: Decimal | None = None
    fouryearpedate: str | None = None
    fouryearpehigher: Decimal | None = None
    fouryearpeaverage: Decimal | None = None
    fouryearpelower: Decimal | None = None
    fouryearavagpehigher: Decimal | None = None
    fouryearavagpemiddle: Decimal | None = None
    fouryearavagpelower: Decimal | None = None
    onequarterpedate: str | None = None
    onequarterpehigher: Decimal | None = None
    onequarterpeaverage: Decimal | None = None
    onequarterpelower: Decimal | None = None
    twoquarterpedate: str | None = None
    twoquarterpehigher: Decimal | None = None
    twoquarterpeaverage: Decimal | None = None
    twoquarterpelower: Decimal | None = None
    threequarterpedate: str | None = None
    threequarterpehigher: Decimal | None = None
    threequarterpeaverage: Decimal | None = None
    threequarterpelower: Decimal | None = None
    fourquarterpedate: str | None = None
    fourquarterpehigher: Decimal | None = None
    fourquarterpeaverage: Decimal | None = None
    fourquarterpelower: Decimal | None = None
    fourquarteravagpehigher: Decimal | None = None
    fourquarteravagpemiddle: Decimal | None = None
    fourquarteravagpelower: Decimal | None = None
    pricehigher: Decimal | None = None
    pricemiddle: Decimal | None = None
    pricelower: Decimal | None = None
    pricequarterhigher: Decimal | None = None
    pricequartermiddle: Decimal | None = None
    pricequarterlower: Decimal | None = None

class YbRoeEpsEntity(BaseDoc):
    __collection__ = "roe_eps"
    id: str | None = Field(default=None, alias="_id")
    date: dt_date | None = None
    code: str | None = None
    name: str | None = None
    value: str | None = None
    price: Decimal | None = None
    pricehigher: Decimal | None = None
    pricemiddle: Decimal | None = None
    pricelower: Decimal | None = None
    valuequarter: str | None = None
    pricequarterhigher: Decimal | None = None
    pricequartermiddle: Decimal | None = None
    pricequarterlower: Decimal | None = None

class DividendYieldEntity(BaseDoc):
    __collection__ = None
    secCode: str | None = None
    secName: str | None = None
    reportYear: str | None = None
    pretaxBonusRmb: float | None = None
    dividendPerShare: float | None = None
    totalShares: float | None = None
    netprofit: float | None = None
    exDividendDate: str | None = None
    exDividendPrice: float | None = None
    dividendYield: float | None = None
    dividendPayoutRatio: float | None = None
    consecutiveYears: int | None = None

class ZqhFinEntity(BaseDoc):
    __collection__ = None
    reportDate: str | None = None
    operatingIncome: float | None = None
    revenueGrowthRate: float | None = None
    netProfit: float | None = None
    netProfitGrowthRate: float | None = None
    operatingGrossProfitMargin: float | None = None
    netInterestRate: float | None = None
    operatingProfitMargin: float | None = None
    returnOnNetAssets: float | None = None
    netOperatingCashFlow: float | None = None
    lAndLiabRatioww: float | None = None


class FreeCashFlowEntity(BaseDoc):
    __collection__ = None
    date: str | None = None
    securityCode: str | None = None
    securityNameAbbr: str | None = None
    operatingCashFlow: float | None = None
    capex: float | None = None
    freeCashFlow: float | None = None
    fcfToNetProfit: float | None = None


class HKItemRow(BaseDoc):
    __collection__ = None
    itemCode: str | None = None
    itemName: str | None = None
    amount: str | None = None


class HKBalanceSheetEntity(BaseDoc):
    __collection__ = "hk_balance_sheet"
    id: str | None = Field(default=None, alias="_id")
    securityCode: str | None = None
    securityNameAbbr: str | None = None
    reportDate: str | None = None
    fiscalYear: str | None = None
    currency: str | None = None
    items: list[HKItemRow] | None = None
    updatedAt: str | datetime | None = None


class HKProfitEntity(BaseDoc):
    __collection__ = "hk_profit"
    id: str | None = Field(default=None, alias="_id")
    securityCode: str | None = None
    securityNameAbbr: str | None = None
    reportDate: str | None = None
    fiscalYear: str | None = None
    basicEps: str | None = None
    dilutedEps: str | None = None
    items: list[HKItemRow] | None = None
    updatedAt: str | datetime | None = None


class HKCashFlowEntity(BaseDoc):
    __collection__ = "hk_cash_flow"
    id: str | None = Field(default=None, alias="_id")
    securityCode: str | None = None
    securityNameAbbr: str | None = None
    reportDate: str | None = None
    fiscalYear: str | None = None
    currency: str | None = None
    items: list[HKItemRow] | None = None
    updatedAt: str | datetime | None = None
