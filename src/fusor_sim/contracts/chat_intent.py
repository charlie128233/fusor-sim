"""ChatIntent: l'unico modo in cui la chat/LLM influenza la configurazione.

La chat non emette mai una RunConfig: propone patch atomiche che
l'orchestratore valida e applica solo negli stati IDLE/PAUSED. La regola
di ownership è verificata già alla costruzione dell'intent: un SET/SCALE
su un campo non di proprietà dell'utente non è nemmeno rappresentabile.
"""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from fusor_sim.contracts.ownership import Owner, owner_of


class ChatAction(str, Enum):
    SET = "SET"  # imposta un valore assoluto
    SCALE = "SCALE"  # moltiplica il valore attuale per un fattore
    ADD_CONSTRAINT = "ADD_CONSTRAINT"  # aggiunge un vincolo (es. da catalogo componenti)
    QUERY = "QUERY"  # domanda, nessuna modifica
    ADD_FORMULA_SOURCE = "ADD_FORMULA_SOURCE"  # aggiunge una fonte al RAG


class ChatIntent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    action: ChatAction
    target: str | None = Field(
        default=None, description="Path nella RunConfig, es. 'physics.pressure_pa'"
    )
    value: float | int | str | bool | None = None
    rationale: str | None = Field(
        default=None, description="Cosa cita dal RAG a supporto della proposta"
    )

    @model_validator(mode="after")
    def _validate_by_action(self) -> "ChatIntent":
        if self.action in (ChatAction.SET, ChatAction.SCALE):
            if self.target is None or self.value is None:
                raise ValueError(f"{self.action.value} richiede sia target sia value")
            owner = owner_of(self.target)  # solleva se il path non esiste
            if owner is not Owner.USER:
                raise ValueError(
                    f"'{self.target}' appartiene a {owner.value}, non all'utente: "
                    "la chat può proporre modifiche solo su geometry e physics"
                )
            if self.action is ChatAction.SCALE and not isinstance(self.value, (int, float)):
                raise ValueError("SCALE richiede un fattore numerico")
        elif self.action is ChatAction.ADD_FORMULA_SOURCE:
            if not isinstance(self.value, str) or not self.value.strip():
                raise ValueError("ADD_FORMULA_SOURCE richiede un riferimento testuale in value")
        return self
