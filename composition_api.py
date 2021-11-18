from main_beanie import *

all_available_commands = {'variants', 'namings', 'contexts', 'effects', 'evidences', 'nuc_positional_mutations',
                          'aa_positional_changes', 'aa_positional_changes', 'nuc_annotations', 'proteins',
                          'protein_regions', 'aa_residue_changes', 'aa_residues', 'aa_residues_ref', 'aa_residues_alt',
                          'sequence', 'host_sample', 'nuc_mutation', 'aa_changes', 'epitopes', 'assays'}

query_with_path_param = re.compile(r'[a-zA-Z_/]+\?[.*^/]')

def do(path: str):
    commands = path.split("/")

    # remove empty commands
    commands = [x for x in commands if x]
    leading_commands = commands[:-1]
    # check leadings are valid
    if not set(leading_commands).issubset(all_available_entities):
        raise MyExceptions.compose_request_unrecognised_command

    trailing_command = commands[-1]

    print(commands)
    print("leading commands", commands[:-1])
    print("trailing command", commands[-1])
    #


if __name__ == '__main__':
    do(input())