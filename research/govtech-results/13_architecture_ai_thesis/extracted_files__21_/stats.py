import sys; sys.path.insert(0,"/home/claude/stupits"); exec(open("scale_exp.py").read().split("print(\"python\"")[0])
r = engine.optimize(top_n=1, data=engine.load_data()); print("ASTANA", r["stats"], r["results"][0].get("score"), r["results"][0].get("cost"))
for n_d,n_m in [(6,14),(8,14),(6,20)]:
    r = engine.optimize(top_n=1, data=CityData(synth(n_d,n_m),source="synthetic")); print(n_d,n_m,r["stats"])
