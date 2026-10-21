"""Minimal stand-in for Domoticz' embedded ``Domoticz`` module, for tests."""
Devices = {}
logs = []


def reset():
    Devices.clear()
    logs.clear()


def Log(text): logs.append(("log", text))
def Error(text): logs.append(("error", text))
def Debug(text): logs.append(("debug", text))
def Status(text): logs.append(("status", text))
def Debugging(flag): logs.append(("debugging", flag))
def Heartbeat(seconds): logs.append(("heartbeat", seconds))


class StubDevice:
    def __init__(self, **kw):
        self.kw = kw
        self.Name = kw["Name"]
        self.Unit = kw["Unit"]
        self.TypeName = kw.get("TypeName")
        # what Domoticz derives from a TypeName (hardwaretypes.h: pTypeGeneral 243, pTypeGeneralSwitch 244)
        self.Type, self.SubType = {"Custom": (243, 31), "Percentage": (243, 6), "Switch": (244, 73)}.get(
            self.TypeName, (kw.get("Type"), kw.get("Subtype")))
        self.SwitchType = kw.get("Switchtype")
        self.Options = kw.get("Options", {})
        self.Description = kw.get("Description", "")
        self.Used = kw.get("Used", 0)
        self.nValue = 0
        self.sValue = ""
        self.updates = 0
        self.deleted = False

    def Update(self, nValue, sValue, Name=None, **_):
        self.nValue, self.sValue = nValue, sValue
        if Name is not None:
            self.Name = Name
        self.updates += 1

    def Delete(self):
        self.deleted = True
        Devices.pop(self.Unit, None)


class Device:
    """``Domoticz.Device(...).Create()`` registers a device."""

    def __init__(self, **kw):
        self.kw = kw

    def Create(self):
        Devices[self.kw["Unit"]] = StubDevice(**self.kw)


def messages(level):
    return [text for lvl, text in logs if lvl == level]


def all_text():
    """Everything that reached the Domoticz log (log, error, debug, status lines) as one string."""
    return "\n".join(str(text) for lvl, text in logs if lvl in ("log", "error", "debug", "status"))
