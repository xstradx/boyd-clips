import os, sys
os.chdir(r"C:\Users\natha\Projects\boyd-clips")
sys.path.insert(0, "research/fit")
import corpus
docs = corpus.load()
print("docs", len(docs))
for d in sorted(docs, key=lambda x: -x["views"])[:3] + sorted(docs, key=lambda x: x["views"])[:3]:
    print(f"{d['id']} views={d['views']:>7} dur={d['dur']:>5} nwords={d['nwords']:>6} "
          f"wpm={d['nwords']/(d['dur']/60):5.1f} turns={d['text'].count('>>'):>4}")
d = docs[0]
print("SAMPLE:", d["text"][:300])
print("WORDS:", d["words"][:12])
