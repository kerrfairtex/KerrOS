
def attach_objective_model(self):
    from agents.supervisor.objectives.objective_model import ObjectiveModel
    self.objective_model = ObjectiveModel()
    return self

def attach_meta_observer(self):
    from agents.supervisor.observer.global_observer import GlobalObserver
    from agents.supervisor.observer.meta_observer import MetaObserver

    self.global_observer = GlobalObserver()
    self.meta_observer = MetaObserver(self.global_observer, getattr(self, "objective_model", None))

    return self
