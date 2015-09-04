import numpy as np
from scipy.optimize import curve_fit
from scipy import stats


values = [(0,16704),(1,36939),(2,13483),(3,6779),(4,4325),(5,2803),(6,2088),(7,1697),(8,1283),(9,976),(10,829),(11,623),(12,512),(13,449),(14,368),(15,300),(16,257),(17,236),(18,238),(19,181),(20,174),(21,171),(22,145),(23,122),(24,104),(25,105),(26,85),(27,66),(28,56),(29,58),(30,58),(31,64),(32,81),(33,37),(34,45),(35,37),(36,33),(37,35),(38,36),(39,17),(40,22),(41,19),(42,16),(43,32),(44,20),(45,15),(46,18),(47,11),(48,8),(49,24),(50,10),(51,22),(52,12),(53,12),(54,12),(55,16),(56,17),(57,12),(58,9),(59,6),(60,2),(61,7),(62,9),(63,5),(64,9),(65,15),(66,10),(67,4),(68,3),(69,4),(70,5),(71,13),(72,5),(73,4),(74,2),(75,5),(76,7),(77,6),(78,4),(79,3),(80,2),(81,2),(82,1),(84,3),(85,2),(86,1),(90,4),(91,1),(92,3),(93,1),(94,3),(95,1),(96,4),(97,2),(98,1),(100,2),(101,1),(104,1),(105,3),(106,1),(108,3),(109,1),(110,1),(113,1),(114,2),(115,2),(116,10),(117,1),(118,1),(119,1)]

def toDistribution(values):
    """
    Converts an array of (x,y) pairs to a distribution object
    """
    xdata, ydata = map(np.array(zip(*values)))

    popt, pcov = curve_fit(normalPDF, xdata, ydata)
    return popt, pcov


def normalPDF(xdata, mu, sigma):
    rv = stats.norm(mu, sigma)
    return rv.pdf(xdata)

def lognormPDF(xdata, mu, sigma):
    """
    If log(x) is normally distributed with mean mu and variance sigma**2
    then x is log-normally distributed with shape parameter sigma and scale parameter exp(mu).
    """
    rv = stats.lognorm(sigma, 0, np.exp(mu))
    return rv.pdf(xdata)

line = np.linspace(1, 10, 100)
realnorm = lognormPDF(line, 1, 3)

popt, pcov = toDistribution(np.array(zip(line, realnorm)))
