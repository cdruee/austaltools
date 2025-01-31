import numpy as np

WIDTHMIN = 1.0
WIDTHSTEP = 0.5

def partition_distance(dist):
    """
    Function to partition distance `dist` into the minimal set of intervals
    that grow approximately exponentially from the edge to the middle,
    are multiples of `WIDTHSTEP` (except the two in the center two),
    have a minimal width of `WIDTHMIN` and
    are symmetrical around the center of L.

    :param dist: distance  to patition
    :type dist: float
    :return: interval widths
    :rtype: list
    """
    # Check that the distance L is within valid range
    if dist < 0.:
        raise ValueError("distance is less than zero")

    if dist < WIDTHMIN:
        res = [dist]
    elif dist < 2. * WIDTHMIN:
        res = [dist / 2.] * 2
    else:
        res = None

        # Initial number of partitions on one side
        minl = 2 * WIDTHMIN
        n = int(np.ceil(dist / minl))
        number = n + 1

        # Iterate until a satisfactory partition is found
        for g in np.linspace(1.,2., 200):
            widths = [WIDTHMIN * g ** i for i in range(n)]

            # Reduce n if we overshoot
            for i in range(len(widths)):
                if np.sum(widths[:i]) > dist/2.:
                    widths = widths[:i]
                    break

            # Check for interval multiples of 0.5
            widths = [round(x / 0.5) * 0.5 for x in widths]

            # Calculate sum and compare to half of L
            r = sum(widths) - dist / 2
            if len(widths) < number and abs(r) <= 0.5:
                widths[-1] -= r
                res = widths + widths[::-1]

        if res is None:
            raise RuntimeError("could not partition distance")

    return res

# Example usage
L = 24.0
intervals = partition_distance(L)
print("Intervals:", intervals)
print("Sum of intervals:", sum(intervals))
