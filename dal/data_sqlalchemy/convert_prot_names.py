import re
import warnings
from typing import Optional

from api_exceptions import MyExceptions

short_protein_name_2_vcm_syntax = {
    "NSP11": "NSP11",
    "NSP13": "NSP13 (helicase)",
    "NSP5": "NSP5 (3C-like proteinase)",
    "NSP12": "NSP12 (RNA-dependent RNA polymerase)",
    "ORF1AB": "ORF1ab polyprotein",
    "ORF7B": "NS7b (ORF7b)",            # CHECK ALIASES
    "NS7B": "NS7b (ORF7b)",             # CHECK ALIASES
    "N": "N (nucleocapsid phosphoprotein)",
    "ORF1A": "ORF1a polyprotein",
    "NSP10": "NSP10",                   # CHECK ALIASES
    "NSP16": "NSP16 (2'-O-ribose methyltransferase)",
    "NSP14": "NSP14 (3'-to-5' exonuclease)",
    "NSP1": "NSP1 (leader protein)",
    "NSP7": "NSP7",
    "NSP3": "NSP3",
    "NS7A": "NS7a (ORF7a protein)",     # CHECK ALIASES
    "ORF7A": "NS7a (ORF7a protein)",    # CHECK ALIASES
    "NSP2": "NSP2",
    "NSP9": "NSP9",
    "NSP6": "NSP6",
    "NSP4": "NSP4",
    "NSP8": "NSP8",
    "NS8": "NS8 (ORF8 protein)",        # CHECK ALIASES
    "ORF8": "NS8 (ORF8 protein)",       # CHECK ALIASES
    "NS6": "NS6 (ORF6 protein)",        # CHECK ALIASES
    "ORF6": "NS6 (ORF6 protein)",       # CHECK ALIASES
    "ORF10": "ORF10 protein",
    "NSP15": "NSP15 (endoRNAse)",
    "S": "Spike (surface glycoprotein)",
    "NS3": "NS3 (ORF3a protein)",       # CHECK ALIASES
    "ORF3A": "NS3 (ORF3a protein)",     # CHECK ALIASES
    "M": "M (membrane glycoprotein)",
    "E": "E (envelope protein)"
}


vcm_syntax_2_short_protein_name = {
    "NSP11": "NSP11",
    "NSP13 (helicase)": "NSP13",
    "NSP5 (3C-like proteinase)": "NSP5",
    "NSP12 (RNA-dependent RNA polymerase)": "NSP12",
    "ORF1ab polyprotein": "ORF1AB",
    # "NS7b (ORF7b)": "ORF7B",  # CHECK ALIASES
    "NS7b (ORF7b)": "NS7B",  # CHECK ALIASES
    "N (nucleocapsid phosphoprotein)": "N",
    "ORF1a polyprotein": "ORF1A",
    "NSP10": "NSP10",  # CHECK ALIASES
    "NSP16 (2'-O-ribose methyltransferase)": "NSP16",
    "NSP14 (3'-to-5' exonuclease)": "NSP14",
    "NSP1 (leader protein)": "NSP1",
    "NSP7": "NSP7",
    "NSP3": "NSP3",
    "NS7a (ORF7a protein)": "NS7A",  # CHECK ALIASES
    # "NS7a (ORF7a protein)": "ORF7A",  # CHECK ALIASES
    "NSP2": "NSP2",
    "NSP9": "NSP9",
    "NSP6": "NSP6",
    "NSP4": "NSP4",
    "NSP8": "NSP8",
    "NS8 (ORF8 protein)": "NS8",  # CHECK ALIASES
    # "NS8 (ORF8 protein)": "ORF8",  # CHECK ALIASES
    "NS6 (ORF6 protein)": "NS6",  # CHECK ALIASES
    # "NS6 (ORF6 protein)": "ORF6",  # CHECK ALIASES
    "ORF10 protein": "ORF10",
    "NSP15 (endoRNAse)": "NSP15",
    "Spike (surface glycoprotein)": "S",
    "NS3 (ORF3a protein)": "NS3",  # CHECK ALIASES
    # "NS3 (ORF3a protein)": "ORF3A",  # CHECK ALIASES
    "M (membrane glycoprotein)": "M",
    "E (envelope protein)": "E"
}


def vcm_aa_change_2_aa_change_id(aa_change_db_obj, suggested_protein: Optional[str] = None):
    if suggested_protein:
        short_prot = suggested_protein
    else:
        short_prot = vcm_syntax_2_short_protein_name[aa_change_db_obj.protein]
    return {
        "aa_change_id": f"{short_prot}:{aa_change_db_obj.reference}{aa_change_db_obj.position}{aa_change_db_obj.alternative}",
        "protein_id": short_prot,
        "reference": aa_change_db_obj.reference,
        "position": aa_change_db_obj.position,
        "alternative": aa_change_db_obj.alternative,
        "type": aa_change_db_obj.type,
        "length": aa_change_db_obj.length
    }


def aa_change_id_2_vcm_aa_change(aa_change_id: str):
    aa_change_re_match = re.fullmatch(r'([a-zA-Z]+):([a-zA-Z\-\*]*)([\d/]+)([a-zA-Z\-\*]+)', aa_change_id.upper())
    if not aa_change_re_match:
        raise MyExceptions.unrecognized_aa_change_id
    else:
        prot, ref, pos, alt = aa_change_re_match.groups()
        prot = prot.upper()
        try:
            prot = short_protein_name_2_vcm_syntax[prot]
        except KeyError:
            if prot.startswith("ORF1A"):
                try:
                    prot, pos = convertORF1ab(prot, int(pos))
                except KeyError:
                    prot = "_"  # assumes the given protein and pos pairs are wrong inputs
            else:
                prot = "_"  # assumes the given protein is wrong
    return prot, ref, int(pos), alt


def kb_nuc_mut_2_vcm_nuc_mut(kb_nuc_mut_id: str):
    kb_nuc_mut_id = kb_nuc_mut_id.lower()
    nuc_positional_mutation_re_match = re.fullmatch(r'([a-zA-Z\-\*]*)([\d/]+)([a-zA-Z\-\*]+)'
                                                    , kb_nuc_mut_id)
    if not nuc_positional_mutation_re_match:
        raise MyExceptions.unrecognised_nuc_positional_mutation_id
    else:
        ref, pos, alt = nuc_positional_mutation_re_match.groups()
        return ref, int(pos), alt


def vcm_nuc_mut_2_kb_nuc_mut(vcm_nuc_mut_id: str):
    return vcm_nuc_mut_id.upper()


def epitope_protein_2_kb_protein(epitope_db_obj, suggested_protein: Optional[str] = None):
    if suggested_protein:
        short_prot = suggested_protein
    else:
        short_prot = vcm_syntax_2_short_protein_name[epitope_db_obj.protein_id]
    return {
        "epitope_id": epitope_db_obj.epitope_id,
        "protein_id": short_prot,
        "host_species": epitope_db_obj.host_species,
        "epitope_start": epitope_db_obj.epitope_start,
        "epitope_stop": epitope_db_obj.epitope_stop
    }


def convertORF1ab(protein, pos):
    # map ORF1A/B to sub-proteins
    if protein == 'ORF1AB' or protein == 'ORF1A':
        if 1 <= pos <= 180:
            protein = "NSP1"
        elif 181 <= pos <= 818:
            pos = pos - 181 + 1
            protein = "NSP2"
        elif 819 <= pos <= 2763:
            pos = pos - 819 + 1
            protein = "NSP3"
        elif 2764 <= pos <= 3263:
            pos = pos - 2764 + 1
            protein = "NSP4"
        elif 3264 <= pos <= 3569:
            pos = pos - 3264 + 1
            protein = "NSP5"
        elif 3570 <= pos <= 3859:
            pos = pos - 3570 + 1
            protein = "NSP6"
        elif 3860 <= pos <= 3942:
            pos = pos - 3860 + 1
            protein = "NSP7"
        elif 3943 <= pos <= 4140:
            pos = pos - 3943 + 1
            protein = "NSP8"
        elif 4141 <= pos <= 4253:
            pos = pos - 4141 + 1
            protein = "NSP9"
        elif 4254 <= pos <= 4392:
            pos = pos - 4254 + 1
            protein = "NSP10"
        elif 4393 <= pos <= 5324:
            pos = pos - 4393 + 1
            protein = "NSP12"
        elif 5325 <= pos <= 5925:
            pos = pos - 5325 + 1
            protein = "NSP13"
        elif 5926 <= pos <= 6452:
            pos = pos - 5926 + 1
            protein = "NSP14"
        elif 6453 <= pos <= 6798:
            pos = pos - 6453 + 1
            protein = "NSP15"
        elif 6799 <= pos <= 7096:
            pos = pos - 6799 + 1
            protein = "NSP16"
        else:
            warnings.warn(f"AA change with protein {protein} and pos {pos} doesn't resolve to any NSP")
        return protein, pos
    elif protein == 'ORF1B':
        if 1 <= pos <= 923:  # 1 -> 923
            pos = pos + 9
            protein = "NSP12"
        elif 924 <= pos <= 1524:  # 924 -> 1524
            pos = pos - 924 + 1
            protein = "NSP13"
        elif 1525 <= pos <= 2051:  # 1525 -> 2051
            pos = pos - 1525 + 1
            protein = "NSP14"
        elif 2052 <= pos <= 2397:  # 2052 ->2397
            pos = pos - 2052 + 1
            protein = "NSP15"
        elif 2398 <= pos <= 2695:  # 2398 -> 2695
            pos = pos - 2398 + 1
            protein = "NSP16"
        else:
            warnings.warn(f"AA change with protein {protein} and pos {pos} doesn't resolve to any NSP")
        return protein, pos
    else:
        raise KeyError(f"Cannot convert coordinates of protein {protein} and pos {pos}")

