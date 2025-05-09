"""
This script takes a TSV file with columns:

locus_ids   (example: "10-100000859-100000887-A" or "10-100000859-100000887-A,10-100001413-100001429-T"
motif       (example: "A")
sample_id:  (example: "HG00609")
allele_size (example: 25)

groups the rows by locus_id and motif columns, and then outputs a table with columns:

locus_id    (example: "10-100001413-100001429-T")
motif       (example: "T")
allele_sizes (example: 25,23,24,24,10,15)
"""

import argparse
import collections
import gzip
import os
import numpy as np
import tqdm
parser = argparse.ArgumentParser()
parser.add_argument("--input-tsv", type=str, default="runs_in_hprc.2025_04.txt.gz")
parser.add_argument("--output-path", type=str, default="runs_in_hprc.2025_04.grouped_by_locus_and_motif.with_biallelic_histogram.tsv.gz")
args = parser.parse_args()

# check that file exists
if not os.path.exists(args.input_tsv):
    parser.error(f"File {args.input_tsv} does not exist")

def process_group(locus_id, motif, allele_sizes, alleles_for_current_key_by_sample_id, output_file):
    """Process a group of allele sizes and write statistics to output file."""
    
    if not allele_sizes:
        return

    if "," in locus_id:
        found_locus_id = None
        for specific_locus_id in locus_id.split(","):
            if specific_locus_id.endswith(f"-{motif}"):
                found_locus_id = specific_locus_id
                break
        else:
            raise ValueError(f"Couldn't resolve locus id for motif {motif} in {locus_id}")

        locus_id = found_locus_id
    
    # Calculate statistics
    allele_sizes = list(sorted(allele_sizes))
    allele_counts = collections.Counter(allele_sizes)
    mode_allele, _ = allele_counts.most_common(1)[0]

    genotype_counts = collections.defaultdict(int)
    for sample_id, allele_list in alleles_for_current_key_by_sample_id.items():
        if len(allele_list) == 1:
            allele_list = allele_list * 2
        elif len(allele_list) != 2:
            raise ValueError(f"Found {len(allele_list)} alleles for {sample_id} in {locus_id} {motif}")

        genotype_counts[tuple(sorted(allele_list))] += 1

    allele_size_histogram = ",".join(f"{allele_size}x:{count}" for allele_size, count in sorted(allele_counts.items()))
    biallelic_histogram = ",".join(f"{genotype[0]}/{genotype[1]}:{count}" for genotype, count in sorted(genotype_counts.items(), key=lambda x: (x[0][1], x[0][0])))

    # Write to output file
    output_file.write("\t".join(map(str, [
        locus_id, 
        motif, 
        allele_size_histogram, 
        biallelic_histogram,
        mode_allele, 
        f"{np.mean(allele_sizes):.3f}",
        f"{np.std(allele_sizes):.3f}", 
        int(np.median(allele_sizes)), 
        int(np.percentile(allele_sizes, 99)), 
    ])) + "\n")

def main():

    print(f"Processing {os.path.basename(args.input_tsv)}")
    infile = gzip.open(args.input_tsv, "rt")
    outfile = gzip.open(args.output_path, "wt")

    # Write header
    outfile.write("\t".join([
        "locus_id", 
        "motif", 
        "allele_size_histogram", 
        "biallelic_histogram",
        "mode_allele", 
        "mean",
        "stdev", 
        "median", 
        "99th_percentile",
    ]) + "\n")

    previous_key = None
    previously_seen_keys = set()
    alleles_for_current_key = []
    alleles_for_current_key_by_sample_id = collections.defaultdict(list)

    sample_ids = set()
    counters = collections.Counter()
    for line_number, line in tqdm.tqdm(enumerate(infile, 1), unit=" rows", unit_scale=True, total=896_015_950):
        fields = line.strip().split("\t")
        if len(fields) != 4:
            print(f"WARNING: Skipping malformed line: {line}")
            continue

        current_locus_id, motif, sample_id, allele_size = fields
        
        sample_ids.add(sample_id)

        current_key = (current_locus_id, motif)
        if previous_key is None:
            previous_key = current_key

        if current_key != previous_key:
            # check that the previous key is not a duplicate
            if previous_key in previously_seen_keys:
                parser.error(f"{args.input_tsv} is not sorted by locus id on line #{line_number}: {current_locus_id}") 
            previously_seen_keys.add(previous_key)

            # process the previous group
            previous_locus_id = previous_key[0]
            previous_motif = previous_key[1]
            previous_key = current_key

            process_group(previous_locus_id, previous_motif, alleles_for_current_key, alleles_for_current_key_by_sample_id, outfile)
            alleles_for_current_key = []
            alleles_for_current_key_by_sample_id = collections.defaultdict(list)
            counters['output_lines'] += 1

        # record the current allele size
        try:
            allele_size = int(allele_size)
            alleles_for_current_key.append(allele_size)
            alleles_for_current_key_by_sample_id[sample_id].append(allele_size)
        except ValueError:
            print(f"Warning: Skipping invalid allele at line #{line_number}: {current_locus_id} {motif} {sample_id} {allele_size}")
            continue
                
    # process the last group
    if alleles_for_current_key:
        process_group(current_locus_id, motif, alleles_for_current_key, alleles_for_current_key_by_sample_id, outfile)
        counters['output_lines'] += 1
        if current_key in previously_seen_keys:
            parser.error(f"{args.input_tsv} is not sorted by locus id on line #{line_number}: {current_locus_id}") 


    infile.close()
    outfile.close()

    print(f"Wrote {counters['output_lines']:9,d} lines to {args.output_path} for {len(sample_ids):9,d} unique sample ids")

if __name__ == "__main__":
    main()