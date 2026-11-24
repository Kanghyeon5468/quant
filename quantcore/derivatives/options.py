import math

from scipy.optimize import brentq
from scipy.stats import norm


def black_scholes(spot, strike, years, rate, volatility, kind='call'):
    if any(not math.isfinite(v) for v in [spot, strike, years, rate, volatility]) or min(spot, strike, years, volatility) <= 0 or kind not in ('call', 'put'):
        raise ValueError('positive finite spot/strike/time/volatility and call/put required')
    d1 = (math.log(spot/strike)+(rate+.5*volatility**2)*years)/(volatility*math.sqrt(years))
    d2 = d1-volatility*math.sqrt(years)
    sign = 1 if kind == 'call' else -1
    discounted = math.exp(-rate*years)
    price = sign*(spot*norm.cdf(sign*d1)-strike*discounted*norm.cdf(sign*d2))
    theta = -spot*norm.pdf(d1)*volatility/(2*math.sqrt(years))-sign*rate*strike*discounted*norm.cdf(sign*d2)
    return {'price': float(price), 'delta': float(sign*norm.cdf(sign*d1)),
        'gamma': float(norm.pdf(d1)/(spot*volatility*math.sqrt(years))),
        'vega_per_vol_point': float(spot*norm.pdf(d1)*math.sqrt(years)/100),
        'theta_per_calendar_day': float(theta/365), 'rho_per_rate_point': float(sign*strike*years*discounted*norm.cdf(sign*d2)/100),
        'assumptions': 'European, no dividends, constant volatility/rate'}


def implied_volatility(price, spot, strike, years, rate, kind='call'):
    return float(brentq(lambda sigma: black_scholes(spot, strike, years, rate, sigma, kind)['price']-price, 1e-6, 5.))
