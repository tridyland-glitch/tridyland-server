from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship, declarative_base
import uuid
from datetime import datetime, timedelta
import secrets

from app.core.database import Base

# ---------------------------------------------------------
# 1. EL USUARIO (El dueño de la experiencia)
# ---------------------------------------------------------
class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, index=True, nullable=False)
    nombre = Column(String, nullable=False)
    
    tiendanube_id = Column(String, nullable=True, doc="ID del cliente en Tiendanube") 
    magic_token = Column(String(64), unique=True, index=True, nullable=True)
    token_expires_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relaciones (La magia de SQLAlchemy)
    tarjetas = relationship("TarjetaQR", back_populates="usuario")
    movimientos = relationship("PuntosLedger", back_populates="usuario")

    def __repr__(self):
        return f"<Usuario(nombre='{self.nombre}', email='{self.email}')>"
    
    def generar_token(self):
        """Genera un token de 32 caracteres y le da 7 días de vida"""
        self.magic_token = secrets.token_urlsafe(32)
        self.token_expires_at = datetime.utcnow() + timedelta(days=7)
        return self.magic_token


# ---------------------------------------------------------
# 2. LA TARJETA QR (El puente entre lo físico y lo digital)
# ---------------------------------------------------------
class TarjetaQR(Base):
    __tablename__ = "tarjetas_qr"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # El código que va en la URL, ej: TRIDY-XYZ98
    codigo = Column(String, unique=True, index=True, nullable=False) 
    
    # ¿Cuántos puntos vale esta tarjeta en este momento?
    puntos_asignados = Column(Integer, default=0) 
    
    # Estados: 'nuevo' (virgen), 'activado' (tú le pusiste saldo), 'ligado' (ya tiene dueño)
    estado = Column(String, default="nuevo", index=True) 
    
    # Si la tarjeta ya fue reclamada, aquí va el ID del dueño
    usuario_id = Column(String(36), ForeignKey("usuarios.id"), nullable=True, index=True)
    
    # Tiempos para auditoría
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    activated_at = Column(DateTime(timezone=True), nullable=True) # Cuando tú la escaneas
    claimed_at = Column(DateTime(timezone=True), nullable=True)   # Cuando el cliente se registra

    # Relaciones
    usuario = relationship("Usuario", back_populates="tarjetas")

    def __repr__(self):
        return f"<TarjetaQR(codigo='{self.codigo}', estado='{self.estado}')>"


# ---------------------------------------------------------
# 3. EL LEDGER (El historial inmutable de puntos)
# ---------------------------------------------------------
class PuntosLedger(Base):
    __tablename__ = "puntos_ledger"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Ahora apuntamos al ID del usuario, no al email
    usuario_id = Column(String(36), ForeignKey("usuarios.id"), nullable=False, index=True)
    
    puntos = Column(Integer, nullable=False, doc="Cantidad (positiva o negativa)")
    accion = Column(String, nullable=False, doc="Ej: 'reclamo_qr_inicial', 'compra_fisica_recurrente', 'canje_recompensa'")
    
    # Opcional pero recomendado: guardar qué tarjeta generó estos puntos (si aplica)
    tarjeta_origen_id = Column(String(36), ForeignKey("tarjetas_qr.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relaciones
    usuario = relationship("Usuario", back_populates="movimientos")

    def __repr__(self):
        return f"<PuntosLedger(usuario_id='{self.usuario_id}', puntos={self.puntos}, accion='{self.accion}')>"