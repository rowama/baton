"""Write the generated parts of the manual (decision 0133). Run after changing the provider directory or provider-notes.yaml."""

from baton import manual_gen

if __name__ == "__main__":
    for rel in manual_gen.write():
        print(rel)
