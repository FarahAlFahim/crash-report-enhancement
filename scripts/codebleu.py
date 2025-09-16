from nltk.translate.bleu_score import sentence_bleu, SmoothingFunction
import re, collections

def weighted_ngram_match(refs, hyps):
    score = 0.0
    for ref, hyp in zip(refs, hyps):
        ref_tokens = ref.split()
        hyp_tokens = hyp.split()

        ref_counts = collections.Counter([tuple(ref_tokens[i:i+ng]) 
                                          for ng in range(1, 5)
                                          for i in range(len(ref_tokens)-ng+1)])
        hyp_counts = collections.Counter([tuple(hyp_tokens[i:i+ng]) 
                                          for ng in range(1, 5)
                                          for i in range(len(hyp_tokens)-ng+1)])
        overlap = sum((ref_counts & hyp_counts).values())
        total = max(1, sum(hyp_counts.values()))
        score += overlap / total
    return score / len(refs)

def dataflow_match(refs, hyps):
    score = 0.0
    var_pattern = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")
    for ref, hyp in zip(refs, hyps):
        ref_vars = set(var_pattern.findall(ref))
        hyp_vars = set(var_pattern.findall(hyp))
        overlap = len(ref_vars & hyp_vars)
        total = max(1, len(hyp_vars))
        score += overlap / total
    return score / len(refs)

def compute_codebleu(references, candidates, lang="java",
                     weights=(0.33, 0.33, 0.0, 0.34)):
    assert len(references) == len(candidates), "Mismatch in refs and hyps length"
    smoothie = SmoothingFunction().method4

    # BLEU (fix: tokenize both sides)
    bleu_scores = [
        sentence_bleu([ref.split() for ref in refs], hyp.split(), smoothing_function=smoothie)
        for refs, hyp in zip(references, candidates)
    ]
    bleu_score = sum(bleu_scores) / len(bleu_scores)

    refs_flat = [" ".join(r[0].split()) for r in references]
    hyps_flat = [" ".join(h.split()) for h in candidates]

    ngram_score = weighted_ngram_match(refs_flat, hyps_flat)
    dataflow_score = dataflow_match(refs_flat, hyps_flat)

    codebleu = (weights[0] * bleu_score +
                weights[1] * ngram_score +
                weights[3] * dataflow_score)

    return {
        "bleu": bleu_score,
        "ngram": ngram_score,
        "syntax": 0.0,  # skipped for Java
        "dataflow": dataflow_score,
        "codebleu": codebleu
    }
