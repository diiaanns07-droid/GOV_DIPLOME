"""A06 experiment E2 (SYNTHETIC grid, not Shymkent).
Close one central street (both directions) and compare:
  level 1: static graph detour (free-flow shortest paths, sumolib), no demand interaction
  level 2: dynamic simulation with the same trips, closingReroute + rerouting
Two demand levels. Same random trips (seeded) for baseline and closure.
"""
import os, subprocess, json, random, xml.etree.ElementTree as ET
import sumolib
OUT = os.path.dirname(os.path.abspath(__file__)) + "/e2"; os.makedirs(OUT, exist_ok=True)
SUMO_HOME = os.environ["SUMO_HOME"]
def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True); return r.returncode, r.stdout + r.stderr

net_file = f"{OUT}/grid.net.xml"
print(run(["netgenerate", "--grid", "--grid.number", "6", "--grid.length", "250", "--default.lanenumber", "1",
           "--default.speed", "13.89", "--tls.guess", "true", "--no-turnarounds", "true", "-o", net_file])[0])
removed = ",".join(f"C{r}D{r},D{r}C{r}" for r in (0,1,3,5))
net_file2 = f"{OUT}/river.net.xml"
print(run(["netconvert", "-s", net_file, "--remove-edges.explicit", removed, "-o", net_file2])[0])
net_file = net_file2
net = sumolib.net.readNet(net_file)
# pick a central horizontal street segment: between nodes C2 and D2 (netgenerate names columns A..F, rows 0..5)
closed = [e.getID() for e in net.getEdges() if e.getID() in ("C2D2", "D2C2")]
print("closed edges:", closed)
triggers = [e.getID() for e in net.getEdges() if e.getID() not in closed]
add = f"""<additional>
  <rerouter id="closure" edges="{' '.join(triggers)}">
    <interval begin="0" end="100000">
      {''.join(f'<closingReroute id="{c}"/>' for c in closed)}
    </interval>
  </rerouter>
</additional>"""
add_file = f"{OUT}/closure.add.xml"; open(add_file, "w").write(add)
ed_tpl = '<additional><edgeData id="ed" file="{f}" begin="0" end="4500"/></additional>'

results = {"closed_edges": closed, "runs": []}
for period in [3.0, 1.2]:  # seconds between trip departures (synthetic demand level)
    trips = f"{OUT}/trips_p{period}.xml"
    rc, log = run(["python3", f"{SUMO_HOME}/tools/randomTrips.py", "-n", net_file, "-o", trips, "-b", "0", "-e", "3600",
                   "-p", str(period), "--seed", "7", "--fringe-factor", "5", "--min-distance", "600", "--validate"])
    assert rc == 0, log[-500:]
    # ---- level 1: static free-flow detour for the same OD pairs ----
    tr = ET.parse(trips).getroot().findall("trip")
    import heapq
    def ff_cost(src_e, dst_e, avoid):
        e0 = net.getEdge(src_e)
        best = {src_e: e0.getLength()/e0.getSpeed()}; pq = [(best[src_e], src_e)]
        while pq:
            d, eid = heapq.heappop(pq)
            if eid == dst_e: return d
            if d > best.get(eid, 1e18): continue
            for nxt in net.getEdge(eid).getOutgoing():
                if avoid and nxt.getID() in closed: continue
                nd = d + nxt.getLength()/nxt.getSpeed()
                if nd < best.get(nxt.getID(), 1e18):
                    best[nxt.getID()] = nd; heapq.heappush(pq, (nd, nxt.getID()))
        return None
    affected, add_ff = 0, []
    for t in tr:
        base = ff_cost(t.get("from"), t.get("to"), False)
        clo = ff_cost(t.get("from"), t.get("to"), True)
        if base is not None and clo is not None and abs(clo - base) > 1e-6:
            affected += 1; add_ff.append(clo - base)
    static = {"trips": len(tr), "affected_trips": affected,
              "mean_added_freeflow_s_affected": round(sum(add_ff)/len(add_ff), 1) if add_ff else 0.0,
              "total_added_freeflow_veh_h": round(sum(add_ff)/3600, 2)}
    # ---- level 2: dynamic ----
    dyn = {}
    for scen, extra in [("baseline", []), ("closure", ["--device.rerouting.probability", "1"])]:
        stat = f"{OUT}/{scen}_p{period}.stat.xml"
        edf = f"{OUT}/{scen}_p{period}.edge.xml"; edadd = f"{OUT}/{scen}_p{period}.ed.add.xml"
        open(edadd, "w").write(ed_tpl.format(f=edf))
        extra = extra + ["-a", ",".join(([add_file] if scen == "closure" else []) + [edadd])]
        run(["sumo", "-n", net_file, "-r", trips, "--end", "4500", "--seed", "42", "--no-step-log", "true",
             "--statistic-output", stat, "--time-to-teleport", "300", "--ignore-route-errors", "true", "--duration-log.statistics", "true"] + extra)
        s = ET.parse(stat).getroot(); v = s.find("vehicles").attrib; ts = s.find("vehicleTripStatistics").attrib
        dyn[scen] = {"loaded": int(v["loaded"]), "inserted": int(v["inserted"]), "running_end": int(v["running"]),
                     "waiting_end": int(v["waiting"]), "teleports": int(s.find("teleports").get("total")),
                     "mean_duration_s": round(float(ts["duration"]), 1), "mean_timeLoss_s": round(float(ts["timeLoss"]), 1),
                     "entered_closed_edges": sum(int(float(e.get("entered", 0))) for e in ET.parse(edf).getroot().iter("edge") if e.get("id") in closed)}
    results["runs"].append({"period_s": period, "veh_per_h": round(3600/period), "static_graph": static, "dynamic": dyn})
    print(json.dumps(results["runs"][-1], ensure_ascii=False))
json.dump(results, open(f"{OUT}/results.json", "w"), indent=1)
