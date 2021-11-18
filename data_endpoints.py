from dal.data_sqlalchemy.model import *


@app.get("/sequences")
async def get_sequences():
    session = get_session()
    seqs = await session.query(Sequence).limit(10).all()
    for x in seqs:
        print(x)
        print(x.sequence_id, x.accession_id)
    return None
