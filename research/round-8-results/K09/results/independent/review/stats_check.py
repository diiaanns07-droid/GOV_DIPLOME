import sys, math
from fractions import Fraction
sys.path.insert(0, "/home/user/GOV_DIPLOME/research/round-8-results/K09")
from k09plan import experiment as X
# nearest-rank index exactness
bad = []
for n in range(1, 5000):
    for q in (0.5, 0.9):
        fl = max(0, math.ceil(q * n) - 1)
        ex = max(0, math.ceil(Fraction(q).limit_denominator(100) * n) - 1)
        if fl != ex: bad.append((n, q, fl, ex))
print("nearest-rank float mismatches (n<5000):", bad[:10], len(bad))
# Wilson vs independent formula
def wil(k, n, z=1.959963984540054):
    p = k/n; a = p + z*z/(2*n); b = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n)); d = 1 + z*z/n
    return (a-b)/d, (a+b)/d
for k, n in [(2043, 2430), (1251, 2430), (0, 30), (30, 30), (17, 30)]:
    print(k, n, X.wilson(k, n), tuple(round(v, 6) for v in wil(k, n)))
# McNemar exact vs independent with Fractions
def mc(b, c):
    n = b + c; k = min(b, c)
    return min(Fraction(1), 2*sum(Fraction(math.comb(n, i), 2**n) for i in range(k+1)))
for b, c in [(846, 55), (1195, 78), (1493, 34), (7, 3), (10, 10)]:
    f = mc(b, c)
    lg = math.log10(f.numerator) - math.log10(f.denominator)
    print(b, c, X.mcnemar_exact(b, c), X.mcnemar_log10(b, c), round(lg, 3))
