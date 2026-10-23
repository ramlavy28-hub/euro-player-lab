"""Descriptive cross-player dispersion, not uncertainty or match-to-match variance."""
import math
import statistics

def describe(values):
    valid=[float(v) for v in values if v is not None and math.isfinite(v)]
    if not valid:
        return {'N':0,'Mean':None,'Variance':None,'Std. deviation':None,'Minimum':None,'Maximum':None,'Zero values':0}
    return {'N':len(valid),'Mean':statistics.mean(valid),'Variance':statistics.pvariance(valid),
            'Std. deviation':statistics.pstdev(valid),'Minimum':min(valid),'Maximum':max(valid),
            'Zero values':sum(v==0 for v in valid)}
