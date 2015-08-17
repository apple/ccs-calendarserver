from twisted.python.filepath import FilePath

class DirectoryRecord(object):
    def __init__(self, uid, password, commonName, email, guid):
        self.uid = uid
        self.password = password
        self.commonName = commonName
        self.email = email
        self.guid = guid

    def __repr__(self):
        return "Record(%s:%s %s %s %s)" % (self.uid, self.password, self.commonName, self.email, self.guid)

# def generateRecords(
#     count, uidPattern="user%d", passwordPattern="user%d",
#     namePattern="User %d", emailPattern="user%d@example.com",
#     guidPattern="user%d"
# ):
#     for i in xrange(count):
#         i += 1
#         uid = uidPattern % (i,)
#         password = passwordPattern % (i,)
#         name = namePattern % (i,)
#         email = emailPattern % (i,)
#         guid = guidPattern % (i,)
#         yield DirectoryRecord(uid, password, name, email, guid)

def recordsFromCSVFile(path):
    if path:
        pathObj = FilePath(path)
    else:
        pathObj = FilePath(__file__).sibling("accounts.csv")
    return [
        DirectoryRecord(*line.decode('utf-8').split(u','))
        for line
        in pathObj.getContent().splitlines()]
