import os, sqlite3, subprocess, shutil, socket, threading, http.server, socketserver, webbrowser
from datetime import datetime
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk, filedialog

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = ImageTk = None

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as ReportLabImage
except ImportError:
    pass

try:
    from geopy.geocoders import Nominatim
    from geopy.exc import GeocoderTimedOut, GeocoderUnavailable
except ImportError:
    pass

try:
    import cv2
except ImportError:
    pass

# --- SERVIDOR HTTP SIMPLE PARA MANUAL ---

class ManualHTTPServer:
    def __init__(self):
        self.server = self.thread = None
        self.port = self._find_free_port()
        self.local_ip = self._get_local_ip()
        self.url = f"http://{self.local_ip}:{self.port}/MANUAL_DE_USUARIO.pdf"

    def _get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip if ip and not ip.startswith('127.') else socket.gethostbyname(socket.gethostname()) or "localhost"
        except: return "localhost"

    def _find_free_port(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            s.listen(1)
            return s.getsockname()[1]

    def start_server(self):
        try:
            class ManualHandler(http.server.SimpleHTTPRequestHandler):
                def do_GET(self):
                    if self.path == '/':
                        html = f"""<!DOCTYPE html><html><head><title>Manual</title><meta name="viewport" content="width=device-width, initial-scale=1.0"><style>body{{font-family:Arial;text-align:center;padding:20px;background:#f5f5f5}}.container{{max-width:600px;margin:0 auto;background:white;padding:30px;border-radius:10px;box-shadow:0 2px 10px rgba(0,0,0,0.1)}}h1{{color:#FF9800}}.download-btn{{background:#FF9800;color:white;padding:15px 30px;text-decoration:none;border-radius:5px;font-size:18px;display:inline-block;margin:20px 0;border:none;cursor:pointer}}</style></head><body><div class="container"><h1>📖 Manual de Usuario</h1><p>Restaurante Preferido</p><a href="/MANUAL_DE_USUARIO.pdf" class="download-btn" download>📥 Descargar Manual</a></div><script>window.onload=function(){{var l=document.createElement('a');l.href='/MANUAL_DE_USUARIO.pdf';l.download='MANUAL_DE_USUARIO.pdf';l.style.display='none';document.body.appendChild(l);l.click();document.body.removeChild(l);}};</script></body></html>"""
                        self.send_response(200)
                        self.send_header('Content-type', 'text/html; charset=utf-8')
                        self.send_header('Access-Control-Allow-Origin', '*')
                        self.end_headers()
                        self.wfile.write(html.encode('utf-8'))
                    elif self.path == '/MANUAL_DE_USUARIO.pdf':
                        try:
                            with open('MANUAL_DE_USUARIO.pdf', 'rb') as f:
                                self.send_response(200)
                                self.send_header('Content-type', 'application/pdf')
                                self.send_header('Access-Control-Allow-Origin', '*')
                                self.end_headers()
                                self.wfile.write(f.read())
                        except: self.send_error(404, "Manual no encontrado")
                    else: self.send_error(404, "Archivo no encontrado")
                def log_message(self, *args): pass
            self.server = socketserver.TCPServer(("0.0.0.0", self.port), ManualHandler)
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            print(f"Servidor HTTP iniciado en {self.local_ip}:{self.port}")
            return True
        except Exception as e:
            print(f"Error al iniciar servidor HTTP: {e}")
            return False

    def stop_server(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            print("Servidor HTTP detenido")

DB_NAME = os.path.join(os.path.dirname(__file__), 'preferido.db')

def inicializar_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios (id INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT UNIQUE, clave TEXT, rol TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS mesas (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, estado TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS productos (id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT UNIQUE, precio REAL, costo REAL DEFAULT 0, cantidad INTEGER DEFAULT 10)''')
    c.execute('''CREATE TABLE IF NOT EXISTS pedidos (id INTEGER PRIMARY KEY AUTOINCREMENT, mesa_id INTEGER, usuario_id INTEGER, estado TEXT, total REAL, fecha TEXT, FOREIGN KEY(mesa_id) REFERENCES mesas(id), FOREIGN KEY(usuario_id) REFERENCES usuarios(id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS detalle_pedido (id INTEGER PRIMARY KEY AUTOINCREMENT, pedido_id INTEGER, producto_id INTEGER, cantidad INTEGER, FOREIGN KEY(pedido_id) REFERENCES pedidos(id), FOREIGN KEY(producto_id) REFERENCES productos(id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS configuracion (id INTEGER PRIMARY KEY AUTOINCREMENT, clave TEXT UNIQUE, valor TEXT)''')
    try: c.execute('DELETE FROM productos WHERE id NOT IN (SELECT MIN(id) FROM productos GROUP BY nombre)')
    except: pass
    c.execute("INSERT OR IGNORE INTO usuarios VALUES (1,'admin','admin','admin')")
    c.execute("INSERT OR IGNORE INTO usuarios VALUES (2,'mozo','mozo','mesero')")
    c.execute("INSERT OR IGNORE INTO usuarios VALUES (3,'cocina','cocina','cocina')")
    for i in range(1,6): c.execute(f"INSERT OR IGNORE INTO mesas VALUES ({i},'Mesa {i}','libre')")
    conn.commit()
    conn.close()

# --- 2. VENTANA DE INICIO DE SESIÓN ---

class LoginWindow:
    def __init__(self, master):
        self.master = master
        master.title('Restaurante Preferido - Inicio de sesión')

        # << MODIFICACIÓN AQUÍ >>: Se mantiene el tamaño y se elimina el fullscreen
        master.geometry('500x800')
        # master.attributes('-fullscreen', True) # COMENTADO/ELIMINADO

        # Centrar la ventana en la pantalla
        self._centrar_ventana()

        # Configurar imagen del logo
        try:
            # Cargar y redimensionar el logo
            logo_path = os.path.join(os.path.dirname(__file__), 'logo.png')
            logo_img = Image.open(logo_path)
            logo_img = logo_img.resize((300, 200), Image.LANCZOS)
            self.logo_photo = ImageTk.PhotoImage(logo_img)

            # Crear label con la imagen centrada
            logo_label = tk.Label(master, image=self.logo_photo, bg='#FF9800')
            logo_label.pack(pady=(20, 10))

            master.configure(bg='#FF9800')
        except Exception as e:
            master.configure(bg='#FF9800')

        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TLabel', background='#FF9800', foreground='white', font=('Arial', 12, 'bold'))
        style.configure('TButton', background='#FFA726', foreground='white', font=('Arial', 12, 'bold'))
        style.configure('TEntry', fieldbackground='#FFF3E0', font=('Arial', 12))

        ttk.Label(master, text='Usuario:').pack(pady=8)
        self.usuario_entry = ttk.Entry(master)
        self.usuario_entry.pack(pady=5)
        ttk.Label(master, text='Clave:').pack(pady=8)
        self.clave_entry = ttk.Entry(master, show='*')
        self.clave_entry.pack(pady=5)

        # Botón de Ingresar
        ttk.Button(master, text='Ingresar', command=self.login).pack(pady=15)
        self.master.bind('<Return>', lambda event: self.login())

        # Botón para cerrar el programa
        ttk.Button(master, text='Cerrar Programa', command=master.destroy).pack(pady=10)

        # Botón para nuestra página web
        ttk.Button(master, text='Nuestra Página Web', command=self.abrir_pagina_web).pack(pady=10)





    def _centrar_ventana(self):
        """Centra la ventana en la pantalla"""
        self.master.update_idletasks()
        width = self.master.winfo_width()
        height = self.master.winfo_height()
        x = (self.master.winfo_screenwidth() // 2) - (width // 2)
        y = (self.master.winfo_screenheight() // 2) - (height // 2)
        self.master.geometry(f'+{x}+{y}')

    def _open_maps(self):
        """Abre Google Maps con la ubicación del restaurante"""
        address = "R. Me. Maria Villac, 2020 - Canasvieiras, Florianópolis - SC, 88054-001, Brasil"
        url = f"https://www.google.com/maps/search/?api=1&query={address.replace(' ', '+')}"
        webbrowser.open(url)

    def ver_video_promocional(self):
        """Abre el video promocional usando el reproductor predeterminado del sistema"""
        try:
            # Usar ruta relativa al directorio del script
            video_path = os.path.join(os.path.dirname(__file__), 'Preferido v.mp4')
            if os.name == 'nt':  # Windows
                os.startfile(video_path)
            elif os.name == 'posix':  # macOS/Linux
                subprocess.run(['open', video_path])  # macOS
                # Para Linux: subprocess.run(['xdg-open', video_path])
        except Exception as e:
            messagebox.showerror('Error', f'No se pudo abrir el video: {e}')

    def abrir_pagina_web(self):
        """Abre la página web del restaurante en el navegador predeterminado"""
        try:
            # Usar ruta relativa al directorio del script
            html_path = os.path.join(os.path.dirname(__file__), 'restaurante.html')
            # Usar file:// protocol para abrir en navegador
            url = f'file://{html_path}'
            webbrowser.open(url)
        except Exception as e:
            messagebox.showerror('Error', f'No se pudo abrir la página web: {e}')



    def login(self):
        usuario = self.usuario_entry.get()
        clave = self.clave_entry.get()
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT id, rol FROM usuarios WHERE usuario=? AND clave=?', (usuario, clave))
        resultado = cursor.fetchone()
        conn.close()
        if resultado:
            self.master.destroy()
            MainWindow(usuario, resultado[1])
        else:
            messagebox.showerror('Error', 'Usuario o clave incorrectos')

# --- 3. VENTANA DE TOMA DE PEDIDO MODAL (COMPACTA) ---

class TomaPedidoWindow:
    def __init__(self, parent_root, mesa, usuario_id, on_success_callback):
        self.parent_root = parent_root
        self.mesa = mesa
        self.usuario_id = usuario_id
        self.on_success_callback = on_success_callback
        self.pedido_detalles = {} # {id_producto: {'cantidad': X, 'precio': Y, 'nombre': Z}}
        
        self.dlg = tk.Toplevel(parent_root)
        self.dlg.title(f'Tomar Pedido - {mesa[1]}')
        # self.dlg.geometry('450x400') # Eliminado para maximizar
        self.dlg.state('zoomed') # Maximizar ventana modal
        self.dlg.transient(parent_root)
        self.dlg.grab_set()

        self.productos_db = self._cargar_productos()
        if not self.productos_db:
            messagebox.showinfo('Error', 'No hay productos definidos en el menú.')
            self.dlg.destroy()
            return
            
        self.productos_nombres = [f'{p[1]} (${p[2]:.2f})' for p in self.productos_db]
        
        self._crear_widgets()

    def _cargar_productos(self):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT id, nombre, precio, cantidad FROM productos WHERE cantidad > 0')
        productos = cursor.fetchall()
        conn.close()
        return productos

    def _crear_widgets(self):
        main_frame = ttk.Frame(self.dlg, padding=10)
        main_frame.pack(fill='both', expand=True)

        # Configurar imagen decorativa organizada
        try:
            # Usar una imagen de WhatsApp como decoración
            decor_img = Image.open('WhatsApp Image 2025-12-20 at 14.20.29 (1).jpeg')
            decor_img = decor_img.resize((150, 105), Image.LANCZOS)
            self.pedido_decor_photo = ImageTk.PhotoImage(decor_img)

            decor_label = tk.Label(main_frame, image=self.pedido_decor_photo, bg='#FF9800')
            decor_label.pack(pady=(0, 10))
        except Exception as e:
            pass

        # Combo Box para seleccionar producto
        ttk.Label(main_frame, text="Selecciona Producto:", font=('Arial', 10, 'bold')).pack(pady=(5, 2))
        self.producto_var = tk.StringVar(self.dlg)
        if self.productos_nombres:
            self.producto_var.set(self.productos_nombres[0]) 
        self.producto_combo = ttk.Combobox(main_frame, textvariable=self.producto_var, values=self.productos_nombres, state='readonly', width=35)
        self.producto_combo.pack(pady=5)

        # Spin Box para cantidad
        ttk.Label(main_frame, text="Cantidad:", font=('Arial', 10, 'bold')).pack(pady=(5, 2))
        self.cantidad_var = tk.IntVar(value=1)
        self.cantidad_spin = ttk.Spinbox(main_frame, from_=1, to=20, textvariable=self.cantidad_var, width=5)
        self.cantidad_spin.pack(pady=5)

        # Botones de acción
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(pady=10)
        
        ttk.Button(btn_frame, text='Añadir', command=self._añadir_producto).pack(side='left', padx=5)
        ttk.Button(btn_frame, text='Finalizar y Enviar', command=self._finalizar_pedido).pack(side='left', padx=5)
        ttk.Button(btn_frame, text='Cancelar', command=self.dlg.destroy).pack(side='left', padx=5)

        # Listado de productos ya agregados
        ttk.Label(main_frame, text="Productos en Pedido:", font=('Arial', 10, 'bold')).pack(pady=(10, 2))
        self.listbox = tk.Listbox(main_frame, height=5, width=45)
        self.listbox.pack(pady=5)
        
        self.dlg.protocol("WM_DELETE_WINDOW", self.dlg.destroy) 
        self.parent_root.wait_window(self.dlg)

    def _añadir_producto(self):
        nombre_seleccionado = self.producto_var.get()
        if not nombre_seleccionado:
            messagebox.showerror('Error', 'Selecciona un producto.')
            return
            
        try:
            cantidad = self.cantidad_var.get()
        except tk.TclError:
            messagebox.showerror('Error', 'Cantidad inválida.')
            return

        if cantidad < 1:
            messagebox.showerror('Error', 'La cantidad debe ser mayor a 0.')
            return

        # Buscar el ID y precio del producto
        producto_info = next((p for p in self.productos_db if f'{p[1]} (${p[2]:.2f})' == nombre_seleccionado), None)

        if producto_info:
            prod_id, nombre, precio, _ = producto_info
            
            # Acumular la cantidad si ya existe
            if prod_id in self.pedido_detalles:
                self.pedido_detalles[prod_id]['cantidad'] += cantidad
            else:
                self.pedido_detalles[prod_id] = {'cantidad': cantidad, 'precio': precio, 'nombre': nombre}
                
            self._actualizar_listbox()
        else:
            messagebox.showerror('Error', 'Selecciona un producto válido de la lista.')
            
    def _actualizar_listbox(self):
        self.listbox.delete(0, tk.END)
        total = 0
        for data in self.pedido_detalles.values():
            subtotal = data['cantidad'] * data['precio']
            self.listbox.insert(tk.END, f"{data['nombre']} x{data['cantidad']} (${subtotal:.2f})")
            total += subtotal
        self.listbox.insert(tk.END, f"-------------------------")
        self.listbox.insert(tk.END, f"TOTAL ACUMULADO: ${total:.2f}")

    def _finalizar_pedido(self):
        if not self.pedido_detalles:
            messagebox.showinfo('Pedido', 'El pedido está vacío.')
            return

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # 1. Crear Pedido (estado inicial pendiente)
        cursor.execute('INSERT INTO pedidos (mesa_id, usuario_id, estado, total) VALUES (?, ?, ?, ?)',
                       (self.mesa[0], self.usuario_id, 'pendiente', 0))
        pedido_id = cursor.lastrowid
        total = 0
        
        # 2. Insertar Detalle y Calcular Total
        for prod_id, data in self.pedido_detalles.items():
            cantidad = data['cantidad']
            precio = data['precio']
            total += precio * cantidad
            cursor.execute('INSERT INTO detalle_pedido (pedido_id, producto_id, cantidad) VALUES (?, ?, ?)',
                           (pedido_id, prod_id, cantidad))
                           
        # 3. Actualizar Total y Mesa
        cursor.execute('UPDATE pedidos SET total=? WHERE id=?', (total, pedido_id))
        cursor.execute('UPDATE mesas SET estado=? WHERE id=?', ('ocupada', self.mesa[0]))

        # 4. Descontar del stock
        for prod_id, data in self.pedido_detalles.items():
            cantidad = data['cantidad']
            cursor.execute('UPDATE productos SET cantidad = cantidad - ? WHERE id = ?', (cantidad, prod_id))

        conn.commit()
        conn.close()
        messagebox.showinfo('Pedido', 'Pedido creado y enviado a cocina.')
        
        self.dlg.destroy()
        self.on_success_callback() # Llama a mostrar_mesas de MainWindow


# --- 4. VENTANA PRINCIPAL (MainWindow) ---

class MainWindow:
    def __init__(self, usuario, rol):
        self.usuario = usuario
        self.rol = rol
        self.root = tk.Tk()
        self.root.title(f'Restaurante Preferido - {self.usuario} ({self.rol})')
        # self.root.geometry('800x550') # Eliminado para FullScreen
        self.root.configure(bg='#FF9800')
        self.root.attributes('-fullscreen', True) # Pantalla completa para la ventana principal

        # Variables de instancia para la gestión de productos
        self.search_entry = None
        self.products_scrollable_frame = None
        self.current_bg_label = None  # Para rastrear el label de fondo actual

        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TLabel', background='#FF9800', foreground='white', font=('Arial', 16, 'bold'))
        style.configure('TButton', background='#FFA726', foreground='white', font=('Arial', 12, 'bold'))
        style.configure('Mesa.TButton', background='#FFA726', foreground='white', font=('Arial', 13, 'bold'))

        self.crear_menu()
        self.pantalla_bienvenida()
        self.root.mainloop()

    def _clear_background(self):
        """Elimina el label de fondo actual si existe"""
        if self.current_bg_label:
            self.current_bg_label.destroy()
            self.current_bg_label = None

    def pantalla_bienvenida(self):
        # Destruir widgets existentes antes de crear la nueva vista
        for widget in self.root.winfo_children():
            widget.destroy()

        # Limpiar fondo anterior
        self._clear_background()

        # Recrear el menú
        self.crear_menu()

        # Configurar imagen decorativa organizada
        try:
            # Usar una de las imágenes de WhatsApp como decoración
            decor_img = Image.open('WhatsApp Image 2025-12-20 at 14.20.29 (1).jpeg')
            decor_img = decor_img.resize((500, 350), Image.LANCZOS)
            self.decor_photo = ImageTk.PhotoImage(decor_img)

            # Crear label con la imagen decorativa en la esquina superior izquierda
            self.current_bg_label = tk.Label(self.root, image=self.decor_photo, bg='#FF9800')
            self.current_bg_label.place(x=10, y=10)

            self.root.configure(bg='#FF9800')
        except Exception as e:
            self.root.configure(bg='#FF9800')

        ttk.Label(self.root, text='¡Bienvenido!', font=('Arial', 28, 'bold')).pack(pady=20)
        ttk.Label(self.root, text='Restaurante Preferido', font=('Arial', 24, 'bold')).pack(pady=10)
        ttk.Label(self.root, text=f'Usuario: {self.usuario} | Rol: {self.rol}', font=('Arial', 16)).pack(pady=10)

        # Determinar el botón de acción principal según el rol
        if self.rol in ['admin', 'mesero']:
             main_action_text = 'Ver Mesas y Pedidos'
        elif self.rol == 'cocina':
             main_action_text = 'Ir al Panel de Cocina'
        else:
             main_action_text = 'Ingresar al sistema'

        ttk.Button(self.root, text=main_action_text, command=self.ir_principal, style='TButton').pack(pady=40)
        ttk.Button(self.root, text='Volver al inicio (Logout)', command=self.volver_inicio, style='TButton').pack(pady=10)

    def ver_video_promocional(self):
        """Abre el video promocional usando el reproductor predeterminado del sistema"""
        video_path = 'Preferido v.mp4'
        try:
            if os.name == 'nt':  # Windows
                os.startfile(video_path)
            elif os.name == 'posix':  # macOS/Linux
                subprocess.run(['open', video_path])  # macOS
                # Para Linux: subprocess.run(['xdg-open', video_path])
        except Exception as e:
            messagebox.showerror('Error', f'No se pudo abrir el video: {e}')

    def volver_inicio(self):
        self.root.destroy()
        # Se debe crear una nueva instancia de Tk para iniciar sesión de nuevo
        new_root = tk.Tk()
        LoginWindow(new_root)
        new_root.mainloop()

    def ir_principal(self):
        for widget in self.root.winfo_children():
            widget.destroy()
        self.crear_menu()
        if self.rol in ['admin', 'mesero']:
            self.mostrar_mesas()
        elif self.rol == 'cocina':
            self.panel_cocina()

    def crear_menu(self):
        menubar = tk.Menu(self.root)
        
        # Administrador tiene todas las opciones
        if self.rol == 'admin':
            menubar.add_command(label='Gestionar productos', command=self.gestionar_productos)
            menubar.add_command(label='Gestionar usuarios', command=self.gestionar_usuarios)
            menubar.add_command(label='Gestionar mesas', command=self.gestionar_mesas)
            menubar.add_command(label='Ver mesas', command=self.mostrar_mesas)
            menubar.add_command(label='Panel de cocina', command=self.panel_cocina)
            menubar.add_command(label='Ver Ventas y Ganancias', command=self.ver_ventas_ganancias)

        # Cocina puede gestionar productos y ver su panel
        elif self.rol == 'cocina':
            menubar.add_command(label='Gestionar productos', command=self.gestionar_productos)
            menubar.add_command(label='Panel de cocina', command=self.panel_cocina)

        # Mesero solo ve mesas
        elif self.rol == 'mesero':
            menubar.add_command(label='Ver mesas', command=self.mostrar_mesas)
        
        menubar.add_command(label='Principal', command=self.pantalla_bienvenida)
        menubar.add_command(label='Salir', command=self.root.destroy)
        self.root.config(menu=menubar)

    def mostrar_mesas(self):
        for widget in self.root.winfo_children():
            widget.destroy()
        self._clear_background()  # Limpiar fondo anterior
        self.crear_menu() # Reasegurar menú

        # Configurar imagen decorativa organizada
        try:
            # Usar otra imagen de WhatsApp como decoración
            decor_img = Image.open('WhatsApp Image 2025-12-20 at 14.20.29 (2).jpeg')
            decor_img = decor_img.resize((500, 350), Image.LANCZOS)
            self.mesas_decor_photo = ImageTk.PhotoImage(decor_img)

            self.current_bg_label = tk.Label(self.root, image=self.mesas_decor_photo, bg='#FF9800')
            self.current_bg_label.place(x=self.root.winfo_screenwidth() - 510, y=10)

            self.root.configure(bg='#FF9800')
        except Exception as e:
            self.root.configure(bg='#FF9800')

        ttk.Label(self.root, text='Mesas').pack(pady=15)
        frame = tk.Frame(self.root, bg='#FF9800')
        frame.pack()
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT id, nombre, estado FROM mesas')
        mesas = cursor.fetchall()
        conn.close()
        for mesa in mesas:
            btn_color = 'green' if mesa[2] == 'libre' else 'red'
            style = ttk.Style()
            style.configure(f'{btn_color}.Mesa.TButton', background=btn_color, foreground='white', font=('Arial', 13, 'bold'))

            btn = ttk.Button(frame, text=f'{mesa[1]} ({mesa[2]})', style=f'{btn_color}.Mesa.TButton', width=22,
                            command=lambda m=mesa: self.seleccionar_mesa(m))
            btn.pack(pady=8, padx=10)

        # Reemplazamos 'Volver' por el botón de la pantalla principal
        ttk.Button(self.root, text='Volver a Principal', command=self.pantalla_bienvenida, style='TButton').pack(pady=15)

    def volver_menu(self):
        # Esta función ya no es necesaria con pantalla_bienvenida()
        self.pantalla_bienvenida()

    def seleccionar_mesa(self, mesa):
        if mesa[2] == 'libre' and self.rol in ['mesero', 'admin']:
            self.iniciar_toma_pedido(mesa)
        elif mesa[2] == 'ocupada':
            # Abre la ventana de gestión de pedidos
            self.ver_pedido(mesa)
        elif mesa[2] == 'libre' and self.rol not in ['mesero', 'admin']:
            messagebox.showinfo('Info', 'Solo el mesero o el administrador pueden crear pedidos.')
        else:
            messagebox.showinfo('Info', 'Mesa cerrada.')

    def iniciar_toma_pedido(self, mesa):
        """Inicia la nueva ventana de Toma de Pedido con el Combobox."""
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM usuarios WHERE usuario=?', (self.usuario,))
        usuario_id = cursor.fetchone()[0]
        conn.close()
        
        # La callback asegura que las mesas se recarguen al finalizar el pedido
        TomaPedidoWindow(self.root, mesa, usuario_id, self.mostrar_mesas)
        
    # === FUNCIÓN PARA GESTIONAR PEDIDO EN MESA OCUPADA ===
    def ver_pedido(self, mesa):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        # Busca pedidos activos que NO estén cerrados
        cursor.execute('SELECT id, estado, total FROM pedidos WHERE mesa_id=? AND estado != "cerrado"', (mesa[0],))
        pedido = cursor.fetchone()
        
        if not pedido:
            conn.close()
            messagebox.showinfo('Info', 'No hay pedido activo en esta mesa.')
            self.mostrar_mesas()
            return
            
        pedido_id = pedido[0]
        pedido_estado = pedido[1]
        pedido_total = pedido[2]
        mesa_id = mesa[0]
        mesa_nombre = mesa[1]
        
        cursor.execute('''SELECT productos.nombre, detalle_pedido.cantidad, productos.precio
                        FROM detalle_pedido JOIN productos ON detalle_pedido.producto_id = productos.id
                        WHERE detalle_pedido.pedido_id=?''', (pedido_id,))
        detalles = cursor.fetchall()
        conn.close()

        # 1. Crear la ventana modal para gestión
        dlg = tk.Toplevel(self.root)
        dlg.title(f'Gestionar Pedido - {mesa_nombre}')
        # dlg.geometry('400x400') # Eliminado para maximizar
        dlg.state('zoomed') # Maximizar ventana modal
        dlg.transient(self.root)
        dlg.grab_set()

        main_frame = ttk.Frame(dlg, padding=10)
        main_frame.pack(fill='both', expand=True)

        # Configurar imagen decorativa organizada
        try:
            # Usar una imagen de WhatsApp como decoración
            decor_img = Image.open('WhatsApp Image 2025-12-20 at 14.20.30.jpeg')
            decor_img = decor_img.resize((150, 105), Image.LANCZOS)
            self.pedido_gestion_decor_photo = ImageTk.PhotoImage(decor_img)

            decor_label = tk.Label(main_frame, image=self.pedido_gestion_decor_photo, bg='#FF9800')
            decor_label.pack(pady=(0, 10))
        except Exception as e:
            pass
        
        ttk.Label(main_frame, text=f'Detalles del Pedido #{pedido_id}', font=('Arial', 14, 'bold')).pack(pady=5)
        ttk.Label(main_frame, text=f'Estado: {pedido_estado} | Total: ${pedido_total:.2f}', font=('Arial', 12)).pack(pady=5)

        # 2. Listado de productos
        list_frame = ttk.Frame(main_frame)
        list_frame.pack(fill='both', expand=True, pady=10)
        
        listbox = tk.Listbox(list_frame, height=10, width=50)
        listbox.pack(side='left', fill='both', expand=True)
        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=listbox.yview)
        scrollbar.pack(side='right', fill='y')
        listbox.config(yscrollcommand=scrollbar.set)
        
        for d in detalles:
            subtotal = d[2] * d[1]
            listbox.insert(tk.END, f"{d[0]} x{d[1]} - ${subtotal:.2f}")

        # 3. Botones de gestión 
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(pady=10)
        
        # Botón 1: Cerrar Pago (Mesero/Admin)
        if self.rol in ['mesero', 'admin']:
            ttk.Button(btn_frame, text='Cerrar Pago y Liberar Mesa', 
                       command=lambda: self.confirmar_pago(dlg, pedido_id, mesa_id)).pack(pady=5)

        # Botón 2: Borrar Pedido (Admin)
        if self.rol == 'admin': # Solo el admin puede cancelar un pedido completo
            ttk.Button(btn_frame, text='Borrar Pedido (Cancelar)', 
                       command=lambda: self.cancelar_pedido(dlg, pedido_id, mesa_id)).pack(pady=5)
                   
        # Botón 3: Volver
        ttk.Button(btn_frame, text='Volver al Panel', command=dlg.destroy).pack(pady=5)
        
        # Esperar que la ventana se cierre
        self.root.wait_window(dlg)
        self.mostrar_mesas() # Recargar la vista de mesas al cerrar la gestión

    def confirmar_pago(self, window, pedido_id, mesa_id):
        if self.rol not in ['mesero', 'admin']:
            messagebox.showerror('Error', 'Permiso denegado.')
            return

        if messagebox.askyesno('Confirmar Pago', '¿Está seguro de conformar el pago y liberar la mesa?'):
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute('UPDATE pedidos SET estado="cerrado", fecha=? WHERE id=?', (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), pedido_id))
            cursor.execute('UPDATE mesas SET estado=? WHERE id=?', ('libre', mesa_id))
            conn.commit()

            # Obtener datos del pedido para la factura
            cursor.execute('''SELECT productos.nombre, detalle_pedido.cantidad, productos.precio
                            FROM detalle_pedido
                            JOIN productos ON detalle_pedido.producto_id = productos.id
                            WHERE detalle_pedido.pedido_id=?''', (pedido_id,))
            detalles = cursor.fetchall()

            # Obtener nombre de la mesa
            cursor.execute('SELECT nombre FROM mesas WHERE id=?', (mesa_id,))
            mesa_result = cursor.fetchone()
            mesa_nombre = mesa_result[0] if mesa_result else 'N/A'

            conn.close()

            # Generar recibo
            filename = self.generar_recibo(pedido_id, mesa_nombre, detalles)
            if filename:
                # Mostrar opciones del recibo (guardar, imprimir, enviar)
                self.mostrar_opciones_recibo(filename, detalles)
            else:
                messagebox.showerror('Error', 'No se pudo generar el recibo PDF.')
            window.destroy()

    def cancelar_pedido(self, window, pedido_id, mesa_id):
        if self.rol not in ['admin']:
            messagebox.showerror('Error', 'Solo el administrador puede cancelar un pedido.')
            return
            
        if messagebox.askyesno('Confirmar Cancelación', 'ADVERTENCIA: ¿Está seguro de CANCELAR y ELIMINAR este pedido? Se liberará la mesa.'):
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            try:
                # 1. Eliminar detalles del pedido
                cursor.execute('DELETE FROM detalle_pedido WHERE pedido_id=?', (pedido_id,))
                # 2. Eliminar el pedido
                cursor.execute('DELETE FROM pedidos WHERE id=?', (pedido_id,))
                # 3. Liberar la mesa
                cursor.execute('UPDATE mesas SET estado=? WHERE id=?', ('libre', mesa_id))
                conn.commit()
                messagebox.showinfo('Pedido', 'Pedido cancelado y eliminado. Mesa liberada.')
            except Exception as e:
                messagebox.showerror('Error', f'Error al cancelar el pedido: {e}')
            conn.close()
            window.destroy()

    def panel_cocina(self):
        for widget in self.root.winfo_children():
            widget.destroy()
        self._clear_background()  # Limpiar fondo anterior
        self.crear_menu() # Reasegurar menú

        # Configurar imagen decorativa organizada
        try:
            # Usar otra imagen de WhatsApp como decoración
            decor_img = Image.open('WhatsApp Image 2025-12-20 at 14.20.29 (3).jpeg')
            decor_img = decor_img.resize((500, 350), Image.LANCZOS)
            self.cocina_decor_photo = ImageTk.PhotoImage(decor_img)

            self.current_bg_label = tk.Label(self.root, image=self.cocina_decor_photo, bg='#FF9800')
            self.current_bg_label.place(x=self.root.winfo_screenwidth() - 510, y=10)

            self.root.configure(bg='#FF9800')
        except Exception as e:
            self.root.configure(bg='#FF9800')

        ttk.Label(self.root, text='Panel de Cocina').pack(pady=15)
        
        # Frame para la lista de pedidos
        list_frame = ttk.Frame(self.root, padding="10")
        list_frame.pack(fill='both', expand=True)

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        # Mostrar solo pedidos pendientes
        cursor.execute('''SELECT pedidos.id, mesas.nombre, pedidos.estado FROM pedidos 
                           JOIN mesas ON pedidos.mesa_id = mesas.id WHERE pedidos.estado="pendiente"''')
        pedidos = cursor.fetchall()

        if not pedidos:
             ttk.Label(list_frame, text='No hay pedidos pendientes.').pack(pady=20)
        else:
            # Treeview para mostrar pedidos de manera más estructurada
            tree = ttk.Treeview(list_frame, columns=("Pedido", "Mesa"), show="headings")
            tree.heading("Pedido", text="Pedido #")
            tree.heading("Mesa", text="Mesa")
            tree.column("Pedido", width=100, anchor='center')
            tree.column("Mesa", width=100, anchor='center')
            tree.pack(side='left', fill='both', expand=True)

            # Scrollbar para el Treeview
            scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
            scrollbar.pack(side='right', fill='y')
            tree.configure(yscrollcommand=scrollbar.set)
            
            # Agregar datos
            for pedido in pedidos:
                tree.insert("", "end", values=(pedido[0], pedido[1]), tags=(pedido[0],))
            
            # Bindeo para ver el detalle al hacer doble clic o seleccionar
            def item_selected(event):
                try:
                    seleccion = tree.selection()
                    if seleccion:
                        pedido_id = tree.item(seleccion[0], 'tags')[0]
                        self.mostrar_detalle_pedido_cocina(int(pedido_id))
                except Exception as e:
                    print(f"Error al seleccionar ítem: {e}")
                    
            tree.bind('<<TreeviewSelect>>', item_selected)
            tree.bind('<Double-1>', item_selected) # Doble clic para mayor usabilidad
            
            # Botón de acción (Marcar como Preparado)
            action_frame = ttk.Frame(self.root)
            action_frame.pack(pady=10)

            # FUNCIÓN MODIFICADA: Ahora incluye confirmación
            def marcar_preparado():
                seleccion = tree.selection()
                if not seleccion:
                    messagebox.showinfo('Cocina', 'Selecciona un pedido para marcar como preparado.')
                    return
                
                # Obtenemos el ID del pedido del tag
                pedido_id = tree.item(seleccion[0], 'tags')[0]
                
                if messagebox.askyesno('Confirmar Plato Listo', f'¿Está seguro de marcar el Pedido #{pedido_id} como LISTO para servir?'):
                    
                    # Usamos una nueva conexión para la transacción de actualización
                    temp_conn = sqlite3.connect(DB_NAME)
                    temp_cursor = temp_conn.cursor()
                    
                    try:
                        temp_cursor.execute('UPDATE pedidos SET estado="preparado" WHERE id=?', (pedido_id,))
                        temp_conn.commit()
                        messagebox.showinfo('Cocina', f'Pedido {pedido_id} marcado como preparado y listo para servir.')
                        self.panel_cocina() # Recargar el panel
                    except Exception as e:
                        messagebox.showerror('Error DB', f'Error al actualizar el estado: {e}')
                    finally:
                        temp_conn.close()

            ttk.Button(action_frame, text='Marcar como Preparado', command=marcar_preparado, style='TButton').pack()


        conn.close() # Cierra la conexión de solo lectura del listado
        ttk.Button(self.root, text='Volver a Principal', command=self.pantalla_bienvenida, style='TButton').pack(pady=15)
        
    # FUNCIÓN CLAVE: Mostrar Detalle del Pedido en Cocina
    def mostrar_detalle_pedido_cocina(self, pedido_id):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # 1. Obtener detalles del pedido (productos y cantidades)
        cursor.execute('''SELECT productos.nombre, detalle_pedido.cantidad
                        FROM detalle_pedido JOIN productos ON detalle_pedido.producto_id = productos.id
                        WHERE detalle_pedido.pedido_id=?''', (pedido_id,))
        detalles = cursor.fetchall()
        
        # 2. Obtener la mesa del pedido
        cursor.execute('''SELECT T2.nombre FROM pedidos AS T1
                        JOIN mesas AS T2 ON T1.mesa_id = T2.id
                        WHERE T1.id = ?''', (pedido_id,))
        mesa_nombre = cursor.fetchone()[0]
        
        conn.close()

        # 3. Crear la ventana modal para el detalle
        dlg = tk.Toplevel(self.root)
        dlg.title(f'Detalle Pedido #{pedido_id} - {mesa_nombre}')
        # dlg.geometry('350x300') # Eliminado para maximizar
        dlg.state('zoomed') # Maximizar ventana modal
        dlg.transient(self.root)
        dlg.grab_set()

        main_frame = ttk.Frame(dlg, padding=10)
        main_frame.pack(fill='both', expand=True)

        # Configurar imagen decorativa organizada
        try:
            # Usar una imagen de WhatsApp como decoración
            decor_img = Image.open('WhatsApp Image 2025-12-20 at 14.20.29 (2).jpeg')
            decor_img = decor_img.resize((150, 105), Image.LANCZOS)
            self.detalle_decor_photo = ImageTk.PhotoImage(decor_img)

            decor_label = tk.Label(main_frame, image=self.detalle_decor_photo, bg='#FF9800')
            decor_label.pack(pady=(0, 10))
        except Exception as e:
            pass

        ttk.Label(main_frame, text=f'Pedido #{pedido_id} para {mesa_nombre}', font=('Arial', 14, 'bold')).pack(pady=10)
        
        # Treeview para el detalle
        tree = ttk.Treeview(main_frame, columns=("Producto", "Cantidad"), show="headings", height=8)
        tree.heading("Producto", text="Producto")
        tree.heading("Cantidad", text="Cantidad")
        tree.column("Producto", width=180, anchor='w')
        tree.column("Cantidad", width=80, anchor='center')
        tree.pack(pady=10)
        
        for nombre, cantidad in detalles:
            tree.insert("", "end", values=(nombre, cantidad))

        ttk.Button(main_frame, text='Cerrar', command=dlg.destroy).pack(pady=10)
        
        self.root.wait_window(dlg)
        
    # --- Métodos de Gestión (Admin y Cocina) ---

    def gestionar_productos(self):
        # Disponible para Admin y Cocina
        for widget in self.root.winfo_children():
            widget.destroy()
        self._clear_background()  # Limpiar fondo anterior
        self.crear_menu() # Reasegurar menú

        # Configurar imagen decorativa organizada
        try:
            # Usar otra imagen de WhatsApp como decoración
            decor_img = Image.open('WhatsApp Image 2025-12-20 at 14.20.30.jpeg')
            decor_img = decor_img.resize((300, 210), Image.LANCZOS)
            self.productos_decor_photo = ImageTk.PhotoImage(decor_img)

            self.current_bg_label = tk.Label(self.root, image=self.productos_decor_photo, bg='#FF9800')
            self.current_bg_label.place(x=self.root.winfo_screenwidth() - 310, y=10)

            self.root.configure(bg='#FF9800')
        except Exception as e:
            self.root.configure(bg='#FF9800')

        ttk.Label(self.root, text='Gestionar Productos').pack(pady=15)

        # 1. Marco de Búsqueda
        search_frame = ttk.Frame(self.root)
        search_frame.pack(pady=10)
        
        ttk.Label(search_frame, text="Buscar:").pack(side='left', padx=5)
        self.search_entry = ttk.Entry(search_frame, width=30)
        self.search_entry.pack(side='left', padx=5)
        
        # Acciones de Búsqueda
        search_command = lambda: self.cargar_productos_en_lista(self.products_scrollable_frame, self.search_entry.get())
        self.search_entry.bind('<Return>', lambda e: search_command())

        ttk.Button(search_frame, text="🔍 Buscar", command=search_command).pack(side='left', padx=5)

        ttk.Button(search_frame, text="Mostrar Todos", 
                   command=lambda: [self.search_entry.delete(0, tk.END), 
                                    self.cargar_productos_en_lista(self.products_scrollable_frame, "")]).pack(side='left', padx=5)


        # 2. Contenedor de Listado (Canvas con Scrollbar)
        canvas_frame = tk.Frame(self.root)
        canvas_frame.pack(fill="both", expand=True, padx=10, pady=5)

        canvas = tk.Canvas(canvas_frame, bg='#FF9800')
        v_scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        
        # La referencia del frame interno se guarda en el objeto para ser accedida por otras funciones
        self.products_scrollable_frame = tk.Frame(canvas, bg='#FF9800') 

        self.products_scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )

        canvas.create_window((0, 0), window=self.products_scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=v_scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        v_scrollbar.pack(side="right", fill="y")
            
        # 3. Carga inicial de productos
        self.cargar_productos_en_lista(self.products_scrollable_frame, "")

        # 4. Botones de acción general
        ttk.Button(self.root, text='➕ Agregar producto', command=self.agregar_producto, style='TButton').pack(pady=15)
        ttk.Button(self.root, text='Volver al Menú Principal', command=self.pantalla_bienvenida, style='TButton').pack(pady=5)
    
    
    def cargar_productos_en_lista(self, frame_container, search_term=""):
        """Carga y muestra la lista de productos filtrada en el frame proporcionado."""

        # 1. Limpiar el frame anterior
        for widget in frame_container.winfo_children():
            widget.destroy()

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # 2. Construir la consulta con o sin filtro
        if search_term:
            # Busqueda case-insensitive y parcial
            cursor.execute('SELECT id, nombre, precio, cantidad FROM productos WHERE nombre LIKE ? ORDER BY nombre',
                           (f'%{search_term}%',))
        else:
            cursor.execute('SELECT id, nombre, precio, cantidad FROM productos ORDER BY nombre')

        productos = cursor.fetchall()
        conn.close()

        if not productos:
            msg = f'No se encontraron productos para "{search_term}".' if search_term else 'No hay productos cargados.'
            ttk.Label(frame_container, text=msg, bg='#FF9800').pack(pady=20)
            # Asegurar que el scroll region se actualice incluso con 0 elementos
            frame_container.update_idletasks()
            return

        # 3. Repoblar la lista con los productos
        for prod in productos:
            prod_frame = tk.Frame(frame_container, bg='#FF9800')
            prod_frame.pack(fill='x', padx=10, pady=5)

            # Mostrar cantidad en stock
            cantidad_color = 'green' if prod[3] > 5 else 'red' if prod[3] > 0 else 'gray'
            ttk.Label(prod_frame, text=f'ID {prod[0]} | {prod[1]} - ${prod[2]:.2f} (Stock: {prod[3]})',
                     foreground=cantidad_color, width=40).pack(side='left', padx=10)

            # Botón Modificar
            ttk.Button(prod_frame, text='Modificar',
                       command=lambda prod_id=prod[0]: self.modificar_producto(prod_id),
                       style='TButton', width=10).pack(side='left', padx=10)

            ttk.Button(prod_frame, text='Borrar',
                       command=lambda prod_id=prod[0]: self.eliminar_producto(prod_id),
                       style='TButton', width=8).pack(side='left', padx=10)

        # 4. Actualizar el área de desplazamiento del canvas
        frame_container.update_idletasks()
        frame_container.master.config(scrollregion=frame_container.master.bbox("all"))


    # FUNCIÓN: MODIFICAR PRODUCTO
    def modificar_producto(self, producto_id):
        # 1. Obtener datos actuales del producto
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT nombre, precio, cantidad FROM productos WHERE id=?', (producto_id,))
        current_data = cursor.fetchone()
        conn.close()

        if not current_data:
            messagebox.showerror('Error', 'Producto no encontrado.')
            # Al fallar, volvemos a cargar la lista actual para limpiar el error
            self.cargar_productos_en_lista(self.products_scrollable_frame, self.search_entry.get())
            return

        current_nombre, current_precio, current_cantidad = current_data

        # 2. Solicitar nuevos valores
        new_nombre = simpledialog.askstring('Modificar Producto', 'Nuevo nombre del producto:', initialvalue=current_nombre)

        if not new_nombre:
            return

        new_precio_str = simpledialog.askstring('Modificar Producto', 'Nuevo precio (ej: 10.50):', initialvalue=f'{current_precio:.2f}')
        if not new_precio_str: return

        try:
            new_precio = float(new_precio_str)
        except ValueError:
            messagebox.showerror('Error', 'Precio inválido. Use números (ej: 10.50).')
            return

        new_cantidad_str = simpledialog.askstring('Modificar Producto', 'Nueva cantidad en stock:', initialvalue=str(current_cantidad))
        if not new_cantidad_str: return

        try:
            new_cantidad = int(new_cantidad_str)
            if new_cantidad < 0:
                messagebox.showerror('Error', 'La cantidad no puede ser negativa.')
                return
        except ValueError:
            messagebox.showerror('Error', 'Cantidad inválida. Use un número entero.')
            return

        # 3. Actualizar la base de datos
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        try:
            # Controlar que el nuevo nombre no exista ya en otro producto
            if new_nombre != current_nombre:
                cursor.execute('SELECT COUNT(*) FROM productos WHERE nombre=? AND id!=?', (new_nombre, producto_id))
                if cursor.fetchone()[0] > 0:
                    messagebox.showerror('Error', f'El nombre "{new_nombre}" ya existe para otro producto.')
                    conn.close()
                    return

            cursor.execute('UPDATE productos SET nombre=?, precio=?, cantidad=? WHERE id=?', (new_nombre, new_precio, new_cantidad, producto_id))
            conn.commit()
            messagebox.showinfo('Producto', 'Producto modificado con éxito.')

        except Exception as e:
            messagebox.showerror('Error', f'Error al modificar el producto: {e}')

        conn.close()

        # 4. Recargar la lista, manteniendo el término de búsqueda actual
        self.cargar_productos_en_lista(self.products_scrollable_frame, self.search_entry.get())


    def agregar_producto(self):
        nombre = simpledialog.askstring('Producto', 'Nombre del producto:')

        if not nombre:
             return

        precio = simpledialog.askfloat('Producto', 'Precio (ej: 10.50):')

        if precio is None:
            return

        cantidad = simpledialog.askinteger('Producto', 'Cantidad en stock (ej: 10):')

        if cantidad is None or cantidad < 0:
            messagebox.showerror('Error', 'La cantidad debe ser un número entero no negativo.')
            return

        if nombre and precio is not None and cantidad is not None:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            try:
                # Se utiliza INSERT OR IGNORE para manejar el UNIQUE constraint de nombre de forma más limpia
                cursor.execute('INSERT OR IGNORE INTO productos (nombre, precio, cantidad) VALUES (?, ?, ?)', (nombre, precio, cantidad))
                if cursor.rowcount == 0:
                     messagebox.showerror('Error', f'El producto "{nombre}" ya existe.')
                else:
                     conn.commit()
                     messagebox.showinfo('Producto', 'Producto agregado.')
            except sqlite3.IntegrityError:
                messagebox.showerror('Error', f'El producto "{nombre}" ya existe. No se agregó.')
            except Exception as e:
                messagebox.showerror('Error', f'Error al agregar el producto: {e}')
            conn.close()

            # Recargar la lista, y limpiar el campo de búsqueda para que se vea el nuevo producto
            self.search_entry.delete(0, tk.END)
            self.cargar_productos_en_lista(self.products_scrollable_frame, "")
            
    def eliminar_producto(self, producto_id):
        # Permite a Cocina y Admin eliminar productos
        if self.rol not in ['admin', 'cocina']:
             messagebox.showerror('Error', 'Permiso denegado. Solo Admin o Cocina pueden eliminar productos.')
             return
             
        if messagebox.askyesno('Confirmar', '¿Estás seguro de que quieres ELIMINAR este producto?'):
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            try:
                # Comprobación de integridad: verificar si el producto está en algún detalle de pedido
                cursor.execute('SELECT COUNT(*) FROM detalle_pedido WHERE producto_id=?', (producto_id,))
                if cursor.fetchone()[0] > 0:
                     messagebox.showerror('Error', 'No se puede eliminar. El producto tiene pedidos asociados. Bórralos primero si es necesario.')
                else:
                    cursor.execute('DELETE FROM productos WHERE id=?', (producto_id,))
                    conn.commit()
                    messagebox.showinfo('Producto', 'Producto eliminado con éxito.')
            except Exception as e:
                messagebox.showerror('Error', f'Error al eliminar el producto: {e}')
            conn.close()
            
            # Recargar la lista, manteniendo el término de búsqueda actual
            self.cargar_productos_en_lista(self.products_scrollable_frame, self.search_entry.get())

    def gestionar_usuarios(self):
        if self.rol != 'admin':
            messagebox.showerror('Error', 'Acceso denegado. Solo el administrador puede gestionar usuarios.')
            self.pantalla_bienvenida()
            return

        for widget in self.root.winfo_children():
            widget.destroy()
        self._clear_background()  # Limpiar fondo anterior
        self.crear_menu()

        # Configurar imagen pequeña decorativa
        try:
            # Usar una imagen de WhatsApp como decoración pequeña
            decor_img = Image.open('WhatsApp Image 2025-12-20 at 14.20.29.jpeg')
            decor_img = decor_img.resize((100, 70), Image.LANCZOS)
            self.usuarios_decor_photo = ImageTk.PhotoImage(decor_img)

            self.current_bg_label = tk.Label(self.root, image=self.usuarios_decor_photo, bg='#FF9800')
            self.current_bg_label.place(x=self.root.winfo_screenwidth() - 110, y=10)

            self.root.configure(bg='#FF9800')
        except Exception as e:
            self.root.configure(bg='#FF9800')

        ttk.Label(self.root, text='Gestionar Usuarios').pack(pady=15)
        frame = tk.Frame(self.root, bg='#FF9800')
        frame.pack()
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT id, usuario, rol FROM usuarios')
        usuarios = cursor.fetchall()
        
        for user in usuarios:
            user_frame = tk.Frame(frame, bg='#FF9800')
            user_frame.pack(fill='x', padx=10, pady=5)
            
            ttk.Label(user_frame, text=f'{user[1]} - {user[2]}', width=30).pack(side='left', padx=10)
            
            if user[1] not in ['admin', 'mozo', 'cocina']: # Evitar borrar usuarios iniciales críticos
                 ttk.Button(user_frame, text='Borrar', 
                            command=lambda user_id=user[0]: self.eliminar_usuario(user_id), 
                            style='TButton', width=8).pack(side='left', padx=10)
                 
        ttk.Button(self.root, text='Agregar usuario', command=self.agregar_usuario).pack(pady=12)
        conn.close()
        ttk.Button(self.root, text='Volver al Menú Principal', command=self.pantalla_bienvenida, style='TButton').pack(pady=15)

    def agregar_usuario(self):
        usuario = simpledialog.askstring('Usuario', 'Nombre de usuario:')
        clave = simpledialog.askstring('Usuario', 'Clave:')
        rol = simpledialog.askstring('Usuario', 'Rol (admin/mesero/cocina):')
        
        if usuario and clave and rol and rol in ['admin', 'mesero', 'cocina']:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            try:
                cursor.execute('INSERT INTO usuarios (usuario, clave, rol) VALUES (?, ?, ?)', (usuario, clave, rol))
                conn.commit()
                messagebox.showinfo('Usuario', 'Usuario agregado.')
            except sqlite3.IntegrityError:
                messagebox.showerror('Error', 'El nombre de usuario ya existe.')
            conn.close()
            self.gestionar_usuarios()
        elif usuario and clave and rol:
             messagebox.showerror('Error', 'Rol inválido. Debe ser admin, mesero o cocina.')

    def eliminar_usuario(self, user_id):
        if messagebox.askyesno('Confirmar', '¿Estás seguro de que quieres ELIMINAR este usuario?'):
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            try:
                cursor.execute('DELETE FROM usuarios WHERE id=?', (user_id,))
                conn.commit()
                messagebox.showinfo('Usuario', 'Usuario eliminado con éxito.')
            except Exception as e:
                messagebox.showerror('Error', f'Error al eliminar el usuario: {e}')
            conn.close()
            self.gestionar_usuarios()


    def gestionar_mesas(self):
        if self.rol != 'admin':
            messagebox.showerror('Error', 'Acceso denegado. Solo el administrador puede gestionar mesas.')
            self.pantalla_bienvenida()
            return

        for widget in self.root.winfo_children():
            widget.destroy()
        self._clear_background()  # Limpiar fondo anterior
        self.crear_menu()

        # Configurar imagen decorativa organizada
        try:
            # Usar otra imagen de WhatsApp como decoración
            decor_img = Image.open('WhatsApp Image 2025-12-20 at 14.20.30 (1).jpeg')
            decor_img = decor_img.resize((200, 140), Image.LANCZOS)
            self.mesas_admin_decor_photo = ImageTk.PhotoImage(decor_img)

            self.current_bg_label = tk.Label(self.root, image=self.mesas_admin_decor_photo, bg='#FF9800')
            self.current_bg_label.place(x=self.root.winfo_screenwidth() - 210, y=10)

            self.root.configure(bg='#FF9800')
        except Exception as e:
            self.root.configure(bg='#FF9800')

        ttk.Label(self.root, text='Gestionar Mesas').pack(pady=15)
        
        # Frame para la lista de mesas
        frame = tk.Frame(self.root, bg='#FF9800')
        frame.pack()
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT id, nombre, estado FROM mesas')
        mesas = cursor.fetchall()
        conn.close()
        
        for mesa in mesas:
            mesa_frame = tk.Frame(frame, bg='#FF9800')
            mesa_frame.pack(fill='x', padx=10, pady=5)
            
            ttk.Label(mesa_frame, text=f'{mesa[1]} - {mesa[2]}', width=30).pack(side='left', padx=10)
            
            if mesa[0] > 5: # Permitir borrar solo mesas añadidas dinámicamente
                 ttk.Button(mesa_frame, text='Borrar', 
                            command=lambda mesa_id=mesa[0]: self.eliminar_mesa(mesa_id), 
                            style='TButton', width=8).pack(side='left', padx=10)

        ttk.Button(self.root, text='Agregar mesa', command=self.agregar_mesa).pack(pady=12)
        ttk.Button(self.root, text='Volver al Menú Principal', command=self.pantalla_bienvenida, style='TButton').pack(pady=15)

    def agregar_mesa(self):
        nombre = simpledialog.askstring('Mesa', 'Nombre de la mesa:')
        if nombre:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            try:
                cursor.execute('INSERT INTO mesas (nombre, estado) VALUES (?, "libre")', (nombre,))
                conn.commit()
                messagebox.showinfo('Mesa', 'Mesa agregada.')
            except sqlite3.IntegrityError:
                messagebox.showerror('Error', 'Ya existe una mesa con ese nombre (no es UNIQUE, pero es buena práctica no duplicar nombres).')
            conn.close()
            self.gestionar_mesas()

    def eliminar_mesa(self, mesa_id):
        if messagebox.askyesno('Confirmar', '¿Estás seguro de que quieres ELIMINAR esta mesa?'):
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            try:
                # Verificar si hay pedidos asociados
                cursor.execute('SELECT COUNT(*) FROM pedidos WHERE mesa_id=? AND estado != "cerrado"', (mesa_id,))
                if cursor.fetchone()[0] > 0:
                     messagebox.showerror('Error', 'No se puede eliminar. Hay pedidos activos asociados a esta mesa.')
                else:
                    cursor.execute('DELETE FROM mesas WHERE id=?', (mesa_id,))
                    conn.commit()
                    messagebox.showinfo('Mesa', 'Mesa eliminada con éxito.')
            except Exception as e:
                messagebox.showerror('Error', f'Error al eliminar la mesa: {e}')
            conn.close()
            self.gestionar_mesas()

    def generar_recibo(self, pedido_id, mesa_nombre, detalles):
        """Genera un recibo en PDF blanco y negro, formato real como recibo térmico"""
        try:
            filename = f'Recibo_Pedido_{pedido_id}.pdf'
            doc = SimpleDocTemplate(filename, pagesize=(80*2.83, 297),  # Ancho típico de recibo térmico
                                   leftMargin=5, rightMargin=5, topMargin=5, bottomMargin=5)
            elements = []

            # Estilos en blanco y negro
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle('Title', parent=styles['Normal'], fontSize=10, alignment=1, fontName='Courier-Bold')
            normal_style = ParagraphStyle('Normal', parent=styles['Normal'], fontSize=8, fontName='Courier')
            bold_style = ParagraphStyle('Bold', parent=styles['Normal'], fontSize=8, fontName='Courier-Bold')

            # Encabezado
            elements.append(Paragraph('RESTAURANTE PREFERIDO', title_style))
            elements.append(Paragraph('Rua Me. Maria Villac, 2020', normal_style))
            elements.append(Paragraph('Florianopolis, SC - Brasil', normal_style))
            elements.append(Paragraph('Tel: (48) 9999-9999', normal_style))
            elements.append(Paragraph('CNPJ: 12.345.678/0001-99', normal_style))
            elements.append(Paragraph('=' * 35, normal_style))
            elements.append(Spacer(1, 5))

            # Información del recibo
            elements.append(Paragraph(f'Recibo #: {pedido_id:04d}', normal_style))
            elements.append(Paragraph(f'Fecha: {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}', normal_style))
            elements.append(Paragraph(f'Mesa: {mesa_nombre}', normal_style))
            elements.append(Paragraph(f'Atendido por: {self.usuario}', normal_style))
            elements.append(Spacer(1, 5))

            # Línea separadora
            elements.append(Paragraph('-' * 35, normal_style))

            # Encabezados de productos
            elements.append(Paragraph('Item                Qtd  Preco  Subtotal', bold_style))

            # Línea separadora
            elements.append(Paragraph('-' * 35, normal_style))

            # Detalles de productos
            total = 0
            for i, (nombre, cantidad, precio) in enumerate(detalles, 1):
                subtotal = cantidad * precio
                total += subtotal
                # Formatear para alinear como recibo real
                nombre_trunc = nombre[:18].ljust(18)
                cant_str = str(cantidad).rjust(3)
                precio_str = f'{precio:.2f}'.rjust(6)
                subtotal_str = f'{subtotal:.2f}'.rjust(8)
                linea = f'{i:2d} {nombre_trunc} {cant_str} {precio_str} {subtotal_str}'
                elements.append(Paragraph(linea, normal_style))

            # Línea separadora
            elements.append(Paragraph('-' * 35, normal_style))

            # Subtotal, IVA y Total
            subtotal_line = f'{"Subtotal:".ljust(27)}${total:.2f}'
            elements.append(Paragraph(subtotal_line, normal_style))
            iva_line = f'{"IVA (2%):".ljust(27)}${total*0.02:.2f}'
            elements.append(Paragraph(iva_line, normal_style))
            total_line = f'{"TOTAL:".ljust(27)}${total*1.02:.2f}'
            elements.append(Paragraph(total_line, bold_style))

            elements.append(Spacer(1, 5))

            # Línea separadora
            elements.append(Paragraph('=' * 35, normal_style))

            # Mensaje de agradecimiento
            elements.append(Paragraph('Obrigado pela sua visita!', normal_style))
            elements.append(Paragraph('Volte sempre!', normal_style))
            elements.append(Paragraph('www.restaurantepreferido.com.br', normal_style))

            # Pie de página
            elements.append(Spacer(1, 10))
            elements.append(Paragraph('*** RECIBO ELETRONICO ***', title_style))
            elements.append(Paragraph('NAO VALE COMO NOTA FISCAL', normal_style))

            # Generar PDF
            doc.build(elements)
            return filename

        except Exception as e:
            messagebox.showerror('Error', f'Error al generar el recibo PDF: {e}')
            return None

    def mostrar_opciones_recibo(self, filename, detalles=None):
        """Muestra ventana emergente con el contenido del recibo centrado y opciones para guardar, enviar e imprimir"""
        # Extraer información del pedido del nombre del archivo
        pedido_id = filename.replace('Recibo_Pedido_', '').replace('.pdf', '')

        # Si no se pasan detalles, obtenerlos de la base de datos
        if detalles is None:
            # Obtener datos del pedido para mostrar
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()

            # Obtener detalles del pedido
            cursor.execute('''SELECT productos.nombre, detalle_pedido.cantidad, productos.precio
                            FROM detalle_pedido JOIN productos ON detalle_pedido.producto_id = productos.id
                            WHERE detalle_pedido.pedido_id=?''', (pedido_id,))
            detalles = cursor.fetchall()

            # Obtener información de la mesa
            cursor.execute('''SELECT mesas.nombre FROM pedidos
                            JOIN mesas ON pedidos.mesa_id = mesas.id
                            WHERE pedidos.id=?''', (pedido_id,))
            mesa_result = cursor.fetchone()
            mesa_nombre = mesa_result[0] if mesa_result else 'N/A'

            conn.close()
        else:
            # Obtener información de la mesa usando el pedido_id
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute('''SELECT mesas.nombre FROM pedidos
                            JOIN mesas ON pedidos.mesa_id = mesas.id
                            WHERE pedidos.id=?''', (pedido_id,))
            mesa_result = cursor.fetchone()
            mesa_nombre = mesa_result[0] if mesa_result else 'N/A'
            conn.close()

        # Crear ventana emergente del recibo
        dlg = tk.Toplevel(self.root)
        dlg.title('Recibo de Pago')
        dlg.geometry('600x700')
        dlg.resizable(True, True)
        dlg.transient(self.root)
        dlg.grab_set()

        # Frame principal centrado
        main_frame = ttk.Frame(dlg, padding=20)
        main_frame.pack(fill='both', expand=True)

        # Contenedor centrado para el contenido del recibo
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(anchor='center')

        # Contenido del recibo centrado
        ttk.Label(content_frame, text='RESTAURANTE PREFERIDO',
                 font=('Courier', 16, 'bold'), foreground='black').pack(pady=(10, 5), anchor='center')
        ttk.Label(content_frame, text='RECIBO DE PAGO',
                 font=('Courier', 14, 'bold'), foreground='black').pack(pady=(0, 20), anchor='center')

        # Información del pedido centrada
        info_frame = ttk.Frame(content_frame)
        info_frame.pack(fill='x', pady=(0, 20))

        ttk.Label(info_frame, text=f'Pedido #: {pedido_id}', font=('Courier', 10)).pack(anchor='center')
        ttk.Label(info_frame, text=f'Mesa: {mesa_nombre}', font=('Courier', 10)).pack(anchor='center')
        ttk.Label(info_frame, text=f'Fecha: {datetime.now().strftime("%d/%m/%Y %H:%M")}', font=('Courier', 10)).pack(anchor='center')
        ttk.Label(info_frame, text=f'Mesero: {self.usuario}', font=('Courier', 10)).pack(anchor='center')

        # Línea separadora
        ttk.Separator(content_frame, orient='horizontal').pack(fill='x', pady=10)

        # Encabezados de la tabla centrados
        headers_frame = ttk.Frame(content_frame)
        headers_frame.pack(fill='x', pady=(10, 5))

        ttk.Label(headers_frame, text='Producto', font=('Courier', 10, 'bold'), width=25, anchor='w').pack(side='left', padx=(0, 5))
        ttk.Label(headers_frame, text='Cant.', font=('Courier', 10, 'bold'), width=6, anchor='e').pack(side='left', padx=(0, 5))
        ttk.Label(headers_frame, text='Precio', font=('Courier', 10, 'bold'), width=8, anchor='e').pack(side='left', padx=(0, 5))
        ttk.Label(headers_frame, text='Subtotal', font=('Courier', 10, 'bold'), width=10, anchor='e').pack(side='left')

        # Línea separadora
        ttk.Separator(content_frame, orient='horizontal').pack(fill='x', pady=5)

        # Detalles de productos
        total = 0
        for nombre, cantidad, precio in detalles:
            subtotal = cantidad * precio
            total += subtotal

            item_frame = ttk.Frame(content_frame)
            item_frame.pack(fill='x', pady=2)

            ttk.Label(item_frame, text=nombre[:25], font=('Courier', 9), width=25, anchor='w').pack(side='left', padx=(0, 5))
            ttk.Label(item_frame, text=str(cantidad), font=('Courier', 9), width=6, anchor='center').pack(side='left', padx=(0, 5))
            ttk.Label(item_frame, text=f'${precio:.2f}', font=('Courier', 9), width=8, anchor='e').pack(side='left', padx=(0, 5))
            ttk.Label(item_frame, text=f'${subtotal:.2f}', font=('Courier', 9), width=10, anchor='e').pack(side='left')

        # Línea separadora
        ttk.Separator(content_frame, orient='horizontal').pack(fill='x', pady=(10, 5))

        # Subtotal
        subtotal_frame = ttk.Frame(content_frame)
        subtotal_frame.pack(fill='x', pady=(5, 2))

        ttk.Label(subtotal_frame, text='Subtotal:', font=('Courier', 10), width=25, anchor='w').pack(side='left', padx=(0, 5))
        ttk.Label(subtotal_frame, text='', width=6, anchor='center').pack(side='left', padx=(0, 5))
        ttk.Label(subtotal_frame, text='', width=8, anchor='e').pack(side='left', padx=(0, 5))
        ttk.Label(subtotal_frame, text=f'${total:.2f}', font=('Courier', 10), width=10, anchor='e').pack(side='left')

        # IVA
        iva = total * 0.02
        iva_frame = ttk.Frame(content_frame)
        iva_frame.pack(fill='x', pady=(2, 5))

        ttk.Label(iva_frame, text='IVA (2%):', font=('Courier', 10), width=25, anchor='w').pack(side='left', padx=(0, 5))
        ttk.Label(iva_frame, text='', width=6, anchor='center').pack(side='left', padx=(0, 5))
        ttk.Label(iva_frame, text='', width=8, anchor='e').pack(side='left', padx=(0, 5))
        ttk.Label(iva_frame, text=f'${iva:.2f}', font=('Courier', 10), width=10, anchor='e').pack(side='left')

        # Total
        total_con_iva = total * 1.02
        total_frame = ttk.Frame(content_frame)
        total_frame.pack(fill='x', pady=(5, 20))

        ttk.Label(total_frame, text='TOTAL:', font=('Courier', 12, 'bold'), width=25, anchor='w').pack(side='left', padx=(0, 5))
        ttk.Label(total_frame, text='', width=6, anchor='center').pack(side='left', padx=(0, 5))
        ttk.Label(total_frame, text='', width=8, anchor='e').pack(side='left', padx=(0, 5))
        ttk.Label(total_frame, text=f'${total_con_iva:.2f}', font=('Courier', 12, 'bold'), width=10, anchor='e').pack(side='left')

        # Mensaje de agradecimiento centrado
        ttk.Label(content_frame, text='¡Gracias por su visita!',
                 font=('Courier', 10, 'italic'), foreground='black').pack(pady=(20, 5), anchor='center')
        ttk.Label(content_frame, text='Esperamos verle pronto nuevamente.',
                 font=('Courier', 10, 'italic'), foreground='black').pack(pady=(0, 30), anchor='center')

        # Botones de acción centrados
        btn_frame = ttk.Frame(content_frame)
        btn_frame.pack(pady=(20, 10))

        def guardar_recibo():
            """Guardar el recibo en una ubicación específica"""
            try:
                from tkinter import filedialog
                save_path = filedialog.asksaveasfilename(
                    defaultextension=".pdf",
                    filetypes=[("PDF files", "*.pdf")],
                    initialfile=filename
                )
                if save_path:
                    shutil.copy2(filename, save_path)
                    messagebox.showinfo('Éxito', f'Recibo guardado en: {save_path}')
            except Exception as e:
                messagebox.showerror('Error', f'Error al guardar: {e}')

        def imprimir_recibo():
            """Imprimir el recibo usando el comando del sistema"""
            try:
                if os.name == 'nt':  # Windows
                    os.startfile(filename, "print")
                elif os.name == 'posix':  # macOS/Linux
                    subprocess.run(['lpr', filename])
                messagebox.showinfo('Imprimir', 'Recibo enviado a impresora')
            except Exception as e:
                messagebox.showerror('Error', f'Error al imprimir: {e}')

        def enviar_recibo():
            """Opción para enviar por email (placeholder)"""
            messagebox.showinfo('Enviar', 'Función de envío por email próximamente disponible')

        ttk.Button(btn_frame, text='💾 Guardar PDF', command=guardar_recibo, style='TButton').pack(side='left', padx=5)
        ttk.Button(btn_frame, text='🖨️ Imprimir', command=imprimir_recibo, style='TButton').pack(side='left', padx=5)
        ttk.Button(btn_frame, text='📧 Enviar', command=enviar_recibo, style='TButton').pack(side='left', padx=5)
        ttk.Button(btn_frame, text='Cerrar', command=dlg.destroy, style='TButton').pack(side='left', padx=5)

        self.root.wait_window(dlg)

    def mostrar_dialogo_pago_completado(self, pedido_id, mesa_nombre, detalles):
        """Muestra un diálogo de confirmación sin opción de imprimir"""
        dlg = tk.Toplevel(self.root)
        dlg.title('Pago Completado')
        dlg.geometry('400x150')
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()

        main_frame = ttk.Frame(dlg, padding=20)
        main_frame.pack(fill='both', expand=True)

        ttk.Label(main_frame, text='✅ Pago confirmado exitosamente',
                 font=('Arial', 14, 'bold')).pack(pady=(10, 5))
        ttk.Label(main_frame, text=f'Mesa {mesa_nombre} liberada',
                 font=('Arial', 12)).pack(pady=(0, 20))

        ttk.Button(main_frame, text='Cerrar',
                  command=dlg.destroy, style='TButton').pack()

        self.root.wait_window(dlg)

    def imprimir_reporte_ventas(self, ganancias_data, productos_vendidos, total_ventas, total_costos, total_ganancias, num_pedidos):
        """Genera e imprime un reporte PDF de ventas y ganancias"""
        try:
            filename = f'Reporte_Ventas_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
            doc = SimpleDocTemplate(filename, pagesize=letter)
            elements = []

            # Estilos
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle('Title', parent=styles['Normal'], fontSize=16, alignment=1, fontName='Helvetica-Bold')
            subtitle_style = ParagraphStyle('Subtitle', parent=styles['Normal'], fontSize=14, fontName='Helvetica-Bold')
            normal_style = ParagraphStyle('Normal', parent=styles['Normal'], fontSize=10, fontName='Helvetica')
            table_style = TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ])

            # Título
            elements.append(Paragraph('REPORTE DE VENTAS Y GANANCIAS', title_style))
            elements.append(Paragraph(f'Generado el: {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}', normal_style))
            elements.append(Spacer(1, 20))

            # Resumen General
            elements.append(Paragraph('RESUMEN GENERAL', subtitle_style))
            elements.append(Spacer(1, 10))

            resumen_data = [
                ['Total de Ventas', f'${total_ventas:.2f}'],
                ['Total de Costos', f'${total_costos:.2f}'],
                ['Total de Ganancias', f'${total_ganancias:.2f}'],
                ['Total de Pedidos', str(num_pedidos)]
            ]

            resumen_table = Table(resumen_data, colWidths=[200, 150])
            resumen_table.setStyle(table_style)
            elements.append(resumen_table)
            elements.append(Spacer(1, 20))

            # Detalle de Pedidos
            if ganancias_data:
                elements.append(Paragraph('DETALLE DE PEDIDOS', subtitle_style))
                elements.append(Spacer(1, 10))

                # Preparar datos para la tabla
                table_data = [['Pedido #', 'Fecha', 'Mesa', 'Mesero', 'Ventas', 'Costos', 'Ganancias']]
                for pedido_id, fecha, total, costos, ganancias, mesa, mesero, semana in ganancias_data[:50]:  # Limitar a 50 registros
                    table_data.append([
                        str(pedido_id),
                        fecha,
                        mesa,
                        mesero,
                        f'${total:.2f}',
                        f'${costos:.2f}',
                        f'${ganancias:.2f}'
                    ])

                # Crear tabla con ajuste de ancho
                col_widths = [60, 100, 60, 80, 80, 80, 80]
                pedidos_table = Table(table_data, colWidths=col_widths)
                pedidos_table.setStyle(table_style)
                elements.append(pedidos_table)
                elements.append(Spacer(1, 20))

            # Productos Más Vendidos
            if productos_vendidos:
                elements.append(Paragraph('PRODUCTOS MÁS VENDIDOS', subtitle_style))
                elements.append(Spacer(1, 10))

                productos_data = [['Producto', 'Unidades', 'Ingresos', 'Costos', 'Ganancias']]
                for nombre, cantidad, ingresos, costos in productos_vendidos:
                    ganancias = ingresos - costos
                    productos_data.append([
                        nombre,
                        str(cantidad),
                        f'${ingresos:.2f}',
                        f'${costos:.2f}',
                        f'${ganancias:.2f}'
                    ])

                productos_table = Table(productos_data, colWidths=[150, 80, 80, 80, 80])
                productos_table.setStyle(table_style)
                elements.append(productos_table)

            # Generar PDF
            doc.build(elements)

            # Abrir el PDF en el navegador
            webbrowser.open(f'file://{os.path.abspath(filename)}')

            messagebox.showinfo('Reporte', f'Reporte generado y abierto en navegador: {filename}')

        except Exception as e:
            messagebox.showerror('Error', f'Error al generar el reporte PDF: {e}')

    def configurar_ubicacion(self):
        """Configura la ubicación del restaurante con Google Maps"""
        if self.rol != 'admin':
            messagebox.showerror('Error', 'Acceso denegado. Solo el administrador puede configurar la ubicación.')
            return

        # Crear ventana modal para configuración
        dlg = tk.Toplevel(self.root)
        dlg.title('Configurar Ubicación del Restaurante')
        dlg.geometry('500x400')
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()

        main_frame = ttk.Frame(dlg, padding=20)
        main_frame.pack(fill='both', expand=True)

        ttk.Label(main_frame, text='Configurar Ubicación', font=('Arial', 16, 'bold')).pack(pady=10)

        # Obtener configuración actual
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT valor FROM configuracion WHERE clave=?', ('direccion',))
        current_direccion = cursor.fetchone()
        current_direccion = current_direccion[0] if current_direccion else ''

        cursor.execute('SELECT valor FROM configuracion WHERE clave=?', ('maps_url',))
        current_maps_url = cursor.fetchone()
        current_maps_url = current_maps_url[0] if current_maps_url else ''
        conn.close()

        # Campo para dirección
        ttk.Label(main_frame, text='Dirección del Restaurante:').pack(anchor='w', pady=(10, 5))
        direccion_entry = ttk.Entry(main_frame, width=50)
        direccion_entry.insert(0, current_direccion)
        direccion_entry.pack(pady=5)

        # Campo para URL de Google Maps
        ttk.Label(main_frame, text='URL de Google Maps:').pack(anchor='w', pady=(10, 5))
        maps_entry = ttk.Entry(main_frame, width=50)
        maps_entry.insert(0, current_maps_url)
        maps_entry.pack(pady=5)

        # Botones
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(pady=20)

        def guardar_ubicacion():
            direccion = direccion_entry.get().strip()
            maps_url = maps_entry.get().strip()

            if not direccion:
                messagebox.showerror('Error', 'La dirección es obligatoria.')
                return

            if not maps_url:
                messagebox.showerror('Error', 'La URL de Google Maps es obligatoria.')
                return

            # Validar que sea una URL de Google Maps
            if 'maps.app.goo.gl' not in maps_url and 'google.com/maps' not in maps_url:
                messagebox.showerror('Error', 'La URL debe ser una dirección válida de Google Maps.')
                return

            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            try:
                # Guardar configuración
                cursor.execute('INSERT OR REPLACE INTO configuracion (clave, valor) VALUES (?, ?)',
                              ('direccion', direccion))
                cursor.execute('INSERT OR REPLACE INTO configuracion (clave, valor) VALUES (?, ?)',
                              ('maps_url', maps_url))
                conn.commit()
                messagebox.showinfo('Éxito', 'Ubicación configurada correctamente.')
                dlg.destroy()
            except Exception as e:
                messagebox.showerror('Error', f'Error al guardar la configuración: {e}')
            finally:
                conn.close()

        def probar_maps():
            maps_url = maps_entry.get().strip()
            if maps_url:
                webbrowser.open(maps_url)
            else:
                messagebox.showerror('Error', 'Ingresa una URL de Google Maps primero.')

        ttk.Button(btn_frame, text='Guardar', command=guardar_ubicacion).pack(side='left', padx=5)
        ttk.Button(btn_frame, text='Probar Maps', command=probar_maps).pack(side='left', padx=5)
        ttk.Button(btn_frame, text='Cancelar', command=dlg.destroy).pack(side='left', padx=5)

        self.root.wait_window(dlg)

    def ver_ventas_ganancias(self):
        """Muestra las ventas y ganancias semanales para el administrador"""
        if self.rol != 'admin':
            messagebox.showerror('Error', 'Acceso denegado. Solo el administrador puede ver las ventas y ganancias.')
            return

        for widget in self.root.winfo_children():
            widget.destroy()
        self._clear_background()
        self.crear_menu()

        # Configurar imagen decorativa organizada
        try:
            # Usar una imagen de WhatsApp como decoración
            decor_img = Image.open('WhatsApp Image 2025-12-20 at 14.20.30.jpeg')
            decor_img = decor_img.resize((200, 140), Image.LANCZOS)
            self.ventas_decor_photo = ImageTk.PhotoImage(decor_img)

            self.current_bg_label = tk.Label(self.root, image=self.ventas_decor_photo, bg='#FF9800')
            self.current_bg_label.place(x=self.root.winfo_screenwidth() - 210, y=10)

            self.root.configure(bg='#FF9800')
        except Exception as e:
            self.root.configure(bg='#FF9800')

        ttk.Label(self.root, text='Ventas y Ganancias Semanales', font=('Arial', 20, 'bold')).pack(pady=20)

        # Frame principal para los datos
        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.pack(fill='both', expand=True)

        # Calcular datos de pedidos individuales
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # Obtener todos los pedidos cerrados con sus detalles
        cursor.execute('''
            SELECT
                pedidos.id,
                pedidos.fecha,
                pedidos.total,
                mesas.nombre as mesa,
                usuarios.usuario as mesero,
                strftime('%Y-%W', pedidos.fecha) as semana
            FROM pedidos
            JOIN mesas ON pedidos.mesa_id = mesas.id
            JOIN usuarios ON pedidos.usuario_id = usuarios.id
            WHERE pedidos.estado = 'cerrado' AND pedidos.fecha IS NOT NULL AND pedidos.fecha != ''
            ORDER BY pedidos.fecha DESC
            LIMIT 50
        ''')
        pedidos_data = cursor.fetchall()

        # Calcular ganancias para cada pedido
        ganancias_data = []
        for pedido_id, fecha, total, mesa, mesero, semana in pedidos_data:
            # Calcular costos para este pedido específico
            cursor.execute('''
                SELECT SUM(detalle_pedido.cantidad * COALESCE(productos.costo, 0)) as costos_totales
                FROM detalle_pedido
                JOIN productos ON detalle_pedido.producto_id = productos.id
                WHERE detalle_pedido.pedido_id = ?
            ''', (pedido_id,))
            costos_result = cursor.fetchone()
            costos = costos_result[0] if costos_result[0] else 0
            ganancias = total - costos
            ganancias_data.append((pedido_id, fecha, total, costos, ganancias, mesa, mesero, semana))

        conn.close()

        # Mostrar datos en una tabla
        if ganancias_data:
            # Crear Treeview para mostrar los datos individuales de pedidos
            tree = ttk.Treeview(main_frame, columns=('Pedido', 'Fecha', 'Mesa', 'Mesero', 'Ventas', 'Costos', 'Ganancias'), show='headings', height=10)
            tree.heading('Pedido', text='Pedido #')
            tree.heading('Fecha', text='Fecha')
            tree.heading('Mesa', text='Mesa')
            tree.heading('Mesero', text='Mesero')
            tree.heading('Ventas', text='Ventas ($)')
            tree.heading('Costos', text='Costos ($)')
            tree.heading('Ganancias', text='Ganancias ($)')

            tree.column('Pedido', width=80, anchor='center')
            tree.column('Fecha', width=120, anchor='center')
            tree.column('Mesa', width=80, anchor='center')
            tree.column('Mesero', width=100, anchor='center')
            tree.column('Ventas', width=100, anchor='e')
            tree.column('Costos', width=100, anchor='e')
            tree.column('Ganancias', width=100, anchor='e')

            # Agregar scrollbar
            scrollbar = ttk.Scrollbar(main_frame, orient='vertical', command=tree.yview)
            tree.configure(yscrollcommand=scrollbar.set)

            tree.pack(side='left', fill='both', expand=True)
            scrollbar.pack(side='right', fill='y')

            # Insertar datos de pedidos individuales
            for pedido_id, fecha, total, costos, ganancias, mesa, mesero, semana in ganancias_data:
                tree.insert('', 'end', values=(
                    pedido_id,
                    fecha,
                    mesa,
                    mesero,
                    f'${total:.2f}',
                    f'${costos:.2f}',
                    f'${ganancias:.2f}'
                ))

            # Calcular y mostrar resumen general
            total_ventas = sum(total for _, _, total, _, _, _, _, _ in ganancias_data)
            total_costos = sum(costos for _, _, _, costos, _, _, _, _ in ganancias_data)
            total_ganancias = sum(ganancias for _, _, _, _, ganancias, _, _, _ in ganancias_data)
            num_pedidos = len(ganancias_data)

            resumen_frame = ttk.Frame(main_frame)
            resumen_frame.pack(fill='x', pady=10)

            ttk.Label(resumen_frame, text='Resumen General:',
                     font=('Arial', 14, 'bold')).pack(pady=5)

            ttk.Label(resumen_frame, text=f'Total de Ventas: ${total_ventas:.2f}',
                     font=('Arial', 12)).pack()
            ttk.Label(resumen_frame, text=f'Total de Costos: ${total_costos:.2f}',
                     font=('Arial', 12)).pack()
            ttk.Label(resumen_frame, text=f'Total de Ganancias: ${total_ganancias:.2f}',
                     font=('Arial', 12, 'bold')).pack(pady=(5, 10))
            ttk.Label(resumen_frame, text=f'Total de Pedidos: {num_pedidos}',
                     font=('Arial', 12)).pack()

            # === SECCIÓN DE PRODUCTOS VENDIDOS ===
            ttk.Label(main_frame, text='Productos Más Vendidos:', font=('Arial', 16, 'bold')).pack(pady=(20, 10))

            # Obtener estadísticas de productos vendidos
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()

            cursor.execute('''
                SELECT
                    productos.nombre,
                    SUM(detalle_pedido.cantidad) as total_vendido,
                    SUM(detalle_pedido.cantidad * productos.precio) as total_ingresos,
                    SUM(detalle_pedido.cantidad * COALESCE(productos.costo, 0)) as total_costos
                FROM detalle_pedido
                JOIN productos ON detalle_pedido.producto_id = productos.id
                JOIN pedidos ON detalle_pedido.pedido_id = pedidos.id
                WHERE pedidos.estado = 'cerrado' AND pedidos.fecha IS NOT NULL AND pedidos.fecha != ''
                GROUP BY productos.id, productos.nombre
                ORDER BY total_vendido DESC
                LIMIT 20
            ''')
            productos_vendidos = cursor.fetchall()
            conn.close()

            if productos_vendidos:
                # Crear Treeview para productos vendidos
                productos_frame = ttk.Frame(main_frame)
                productos_frame.pack(fill='both', expand=True, pady=(0, 20))

                productos_tree = ttk.Treeview(productos_frame, columns=('Producto', 'Cantidad', 'Ingresos', 'Costos', 'Ganancias'), show='headings', height=8)
                productos_tree.heading('Producto', text='Producto')
                productos_tree.heading('Cantidad', text='Unidades Vendidas')
                productos_tree.heading('Ingresos', text='Ingresos ($)')
                productos_tree.heading('Costos', text='Costos ($)')
                productos_tree.heading('Ganancias', text='Ganancias ($)')

                productos_tree.column('Producto', width=150, anchor='w')
                productos_tree.column('Cantidad', width=120, anchor='center')
                productos_tree.column('Ingresos', width=100, anchor='e')
                productos_tree.column('Costos', width=100, anchor='e')
                productos_tree.column('Ganancias', width=100, anchor='e')

                # Scrollbar para productos
                prod_scrollbar = ttk.Scrollbar(productos_frame, orient='vertical', command=productos_tree.yview)
                productos_tree.configure(yscrollcommand=prod_scrollbar.set)

                productos_tree.pack(side='left', fill='both', expand=True)
                prod_scrollbar.pack(side='right', fill='y')

                # Insertar datos de productos
                for nombre, cantidad, ingresos, costos in productos_vendidos:
                    ganancias = ingresos - costos
                    productos_tree.insert('', 'end', values=(
                        nombre,
                        cantidad,
                        f'${ingresos:.2f}',
                        f'${costos:.2f}',
                        f'${ganancias:.2f}'
                    ))
            else:
                ttk.Label(main_frame, text='No hay datos de productos vendidos.',
                         font=('Arial', 12)).pack(pady=10)
        else:
            ttk.Label(main_frame, text='No hay datos de ventas disponibles.',
                     font=('Arial', 14)).pack(pady=50)

        # Botón para imprimir el reporte
        ttk.Button(self.root, text='🖨️ Imprimir Reporte', command=lambda: self.imprimir_reporte_ventas(ganancias_data, productos_vendidos, total_ventas, total_costos, total_ganancias, num_pedidos), style='TButton').pack(pady=10)
        ttk.Button(self.root, text='Volver al Menú Principal', command=self.pantalla_bienvenida, style='TButton').pack(pady=20)

# --- 5. PUNTO DE ENTRADA ---

if __name__ == '__main__':
    inicializar_db()
    root = tk.Tk()
    app = LoginWindow(root)
    root.mainloop()