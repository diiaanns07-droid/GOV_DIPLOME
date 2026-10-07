"""A06 experiment E1 (SYNTHETIC). Not Shymkent data.
Variants of one 4-leg crossing:
  A  at-grade, signalised (netconvert default static TLS)
  B  flyover without ramps: W-E edge passes over the crossing, no shared node
  C  flyover (W-E through on upper level) + roundabout below with ramps
Checks: (1) connectivity of turns in B; (2) sensitivity of metrics to demand mix/level.
"""
import os, subprocess, json, itertools, xml.etree.ElementTree as ET
OUT = os.path.dirname(os.path.abspath(__file__)) + "/e1"
os.makedirs(OUT, exist_ok=True)

def w(name, text):
    p = f"{OUT}/{name}"; open(p, "w").write(text); return p

def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr)

# ---------- networks (plain XML) ----------
NODE_COMMON = """
  <node id="W" x="-600" y="0" type="priority"/>  <node id="E" x="600" y="0" type="priority"/>
  <node id="N" x="0" y="600" type="priority"/>   <node id="S" x="0" y="-600" type="priority"/>"""
def two_way(a, b, lanes=2, speed=16.67, shape=None, eid=None):
    eid = eid or f"{a}{b}"
    sh = f' shape="{shape}"' if shape else ""
    return (f'  <edge id="{eid}" from="{a}" to="{b}" numLanes="{lanes}" speed="{speed}"{sh}/>\n'
            f'  <edge id="{eid}_r" from="{b}" to="{a}" numLanes="{lanes}" speed="{speed}"/>\n')

nets = {}
# A: at-grade signalised
nodes = f"<nodes>{NODE_COMMON}\n  <node id='C' x='0' y='0' type='traffic_light'/>\n</nodes>"
edges = "<edges>\n" + two_way("W","C",eid="WC") + two_way("C","E",eid="CE") + two_way("N","C",eid="NC") + two_way("C","S",eid="CS") + "</edges>"
nets["A"] = (nodes, edges)
# B: flyover without ramps -> W-E and N-S cross geometrically, no common node
nodes = f"<nodes>{NODE_COMMON}\n</nodes>"
edges = "<edges>\n" + two_way("W","E",eid="WE") + two_way("N","S",eid="NS") + "</edges>"
nets["B"] = (nodes, edges)
# C: upper through W-E (Wd<->Ed), roundabout below, ramps to/from it, N-S into roundabout
nodes = f"""<nodes>{NODE_COMMON}
  <node id="Wd" x="-200" y="0" type="priority"/> <node id="Ed" x="200" y="0" type="priority"/>
  <node id="rn" x="0" y="45" type="priority"/> <node id="rw" x="-45" y="0" type="priority"/>
  <node id="rs" x="0" y="-45" type="priority"/> <node id="re" x="45" y="0" type="priority"/>
</nodes>"""
edges = "<edges>\n" + two_way("W","Wd",eid="WWd") + two_way("Ed","E",eid="EdE")
edges += '  <edge id="UP_E" from="Wd" to="Ed" numLanes="2" speed="16.67" shape="-200,8 200,8"/>\n'
edges += '  <edge id="UP_W" from="Ed" to="Wd" numLanes="2" speed="16.67" shape="200,14 -200,14"/>\n'
# ramps (1 lane): eastbound off at Wd -> rw, on re -> Ed ; westbound off Ed -> re, on rw -> Wd
edges += '  <edge id="offE" from="Wd" to="rw" numLanes="1" speed="11.1" shape="-200,-6 -45,-6"/>\n'
edges += '  <edge id="onE" from="re" to="Ed" numLanes="1" speed="11.1" shape="45,-6 200,-6"/>\n'
edges += '  <edge id="offW" from="Ed" to="re" numLanes="1" speed="11.1" shape="200,-12 45,-12"/>\n'
edges += '  <edge id="onW" from="rw" to="Wd" numLanes="1" speed="11.1" shape="-45,-12 -200,-12"/>\n'
edges += two_way("N","rn",eid="Nrn") + two_way("rs","S",eid="rsS")
# roundabout counter-clockwise (right-hand traffic): rn->rw->rs->re->rn, 1 lane
for a,b in [("rn","rw"),("rw","rs"),("rs","re"),("re","rn")]:
    edges += f'  <edge id="ring_{a}{b}" from="{a}" to="{b}" numLanes="1" speed="8.33"/>\n'
edges += "</edges>"
nets["C"] = (nodes, edges)

net_files = {}
for k,(n,e) in nets.items():
    nf, ef = w(f"{k}.nod.xml", n), w(f"{k}.edg.xml", e)
    out = f"{OUT}/{k}.net.xml"
    rc, log = run(["netconvert", "-n", nf, "-e", ef, "-o", out, "--no-turnarounds", "true",
                   "--roundabouts.guess", "true", "--tls.default-type", "static"])
    net_files[k] = out
    print(f"netconvert {k}: rc={rc}", ("WARN: " + log.strip().splitlines()[0]) if "Warning" in log else "")

# ---------- connectivity check for B ----------
import sumolib
res_conn = {}
for k in net_files:
    net = sumolib.net.readNet(net_files[k])
    # does any node exist at the crossing and is there a path W->S?
    src = net.getEdge({"A":"WC","B":"WE","C":"WWd"}[k])
    dst = net.getEdge({"A":"CS","B":"NS","C":"rsS"}[k])
    path, cost = net.getShortestPath(src, dst)
    res_conn[k] = {"nodes": len(net.getNodes()), "W_to_S_route_exists": path is not None,
                   "W_to_S_edges": [e.getID() for e in path] if path else None}
print("connectivity:", json.dumps(res_conn, ensure_ascii=False))

# ---------- demand: flows by OD, two mixes x three levels ----------
OD = {  # origin edge, destination edge per variant
 "A": {"W":"WC","E":"CE_r","N":"NC","S":"CS_r"}, "C": {"W":"WWd","E":"EdE_r","N":"Nrn","S":"rsS_r"}}
DEST = {"A": {"W":"WC_r","E":"CE","N":"NC_r","S":"CS"}, "C": {"W":"WWd_r","E":"EdE","N":"Nrn_r","S":"rsS"}}
MIXES = {  # share of each origin's volume that goes straight (rest split left/right equally)
 "through_heavy": {"WE_share": 0.65, "straight": 0.8},
 "turn_heavy":    {"WE_share": 0.50, "straight": 0.4},
}
LEVELS = [1200, 2400, 3600]  # total veh/h entering (synthetic)
OPP = {"W":"E","E":"W","N":"S","S":"N"}
LEFT = {"W":"N","E":"S","N":"E","S":"W"}   # right-hand traffic: heading east from W, left turn goes north
RIGHT = {"W":"S","E":"N","N":"W","S":"E"}

def routes_file(variant, mix, total):
    m = MIXES[mix]; lines = ['<routes>', '  <vType id="car" length="4.5" minGap="2.5"/>']
    vol = {"W": total*m["WE_share"]/2, "E": total*m["WE_share"]/2,
           "N": total*(1-m["WE_share"])/2, "S": total*(1-m["WE_share"])/2}
    i = 0
    for o, v in vol.items():
        for d, sh in [(OPP[o], m["straight"]), (LEFT[o], (1-m["straight"])/2), (RIGHT[o], (1-m["straight"])/2)]:
            q = v*sh
            if q <= 0: continue
            lines.append(f'  <flow id="f{i}_{o}{d}" type="car" begin="0" end="3600" vehsPerHour="{q:.1f}" '
                         f'from="{OD[variant][o]}" to="{DEST[variant][d]}" departLane="best" departSpeed="max"/>')
            i += 1
    lines.append("</routes>")
    return w(f"{variant}_{mix}_{total}.rou.xml", "\n".join(lines))

rows = []
for variant, mix, total in itertools.product(["A","C"], MIXES, LEVELS):
    rf = routes_file(variant, mix, total)
    stat = f"{OUT}/{variant}_{mix}_{total}.stat.xml"
    rc, log = run(["sumo", "-n", net_files[variant], "-r", rf, "--begin", "0", "--end", "4500",
                   "--seed", "42", "--no-step-log", "true", "--statistic-output", stat,
                   "--duration-log.statistics", "true", "--time-to-teleport", "300"])
    s = ET.parse(stat).getroot()
    veh = s.find("vehicles").attrib; tp = s.find("teleports").attrib; ts = s.find("vehicleTripStatistics").attrib
    rows.append({"variant": variant, "mix": mix, "demand_vph": total,
                 "inserted": int(veh["inserted"]), "running_at_end": int(veh["running"]),
                 "waiting_insert_at_end": int(veh["waiting"]), "teleports": int(tp["total"]),
                 "mean_duration_s": round(float(ts["duration"]),1), "mean_timeLoss_s": round(float(ts["timeLoss"]),1),
                 "mean_routeLength_m": round(float(ts["routeLength"]),1)})
    print(rows[-1])
json.dump({"connectivity": res_conn, "runs": rows}, open(f"{OUT}/results.json","w"), indent=1)
