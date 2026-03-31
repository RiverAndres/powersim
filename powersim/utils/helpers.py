
def calculate_time_deltas(time_index) -> dict:
    """
    Devuelve un dict:
        {t: delta_t_en_horas}
    El último timestep usa el mismo dt que el anterior.
    """
    deltas = {}

    for i, t in enumerate(time_index):
        if i < len(time_index) - 1:
            dt = (time_index[i + 1] - t).total_seconds() / 3600
        else:
            dt = (t - time_index[i - 1]).total_seconds() / 3600

        deltas[t] = dt

    return deltas