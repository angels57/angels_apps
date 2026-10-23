import { Component } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { useProps, useState } from "@angels_flow/common/owl_compat";

/**
 * Font Awesome 4 icons offered for a form, by theme. The words help the
 * search in English and Spanish, whatever the language of the user.
 */
const ICON_GROUPS = [
    {
        label: _t("Travel"),
        icons: [
            ["fa-plane", "plane avion viaje travel flight vuelo"],
            ["fa-car", "car coche auto vehiculo vehicle"],
            ["fa-bus", "bus autobus transport transporte"],
            ["fa-train", "train tren"],
            ["fa-bed", "bed hotel cama alojamiento accommodation"],
            ["fa-suitcase", "suitcase maleta equipaje luggage"],
            ["fa-map-marker", "map mapa location ubicacion lugar place"],
            ["fa-globe", "globe mundo world internacional"],
        ],
    },
    {
        label: _t("Money"),
        icons: [
            ["fa-money", "money dinero cash efectivo pago payment"],
            ["fa-credit-card", "card tarjeta credito credit pago"],
            ["fa-calculator", "calculator calculadora presupuesto budget"],
            ["fa-shopping-cart", "cart carrito compra purchase shopping"],
            ["fa-university", "bank banco"],
            ["fa-line-chart", "chart grafico ventas sales"],
            ["fa-percent", "percent porcentaje descuento discount"],
            ["fa-gift", "gift regalo"],
        ],
    },
    {
        label: _t("People"),
        icons: [
            ["fa-user", "user usuario persona person"],
            ["fa-users", "users equipo team grupo group"],
            ["fa-id-card-o", "id card identificacion empleado employee"],
            ["fa-user-plus", "hire contratar alta onboarding nuevo"],
            ["fa-handshake-o", "handshake acuerdo deal contrato"],
            ["fa-graduation-cap", "training formacion curso course"],
            ["fa-heartbeat", "health salud medico medical"],
            ["fa-child", "child hijo familia family"],
        ],
    },
    {
        label: _t("Documents"),
        icons: [
            ["fa-file-text-o", "file archivo documento document formulario form"],
            ["fa-file-pdf-o", "pdf"],
            ["fa-folder-open-o", "folder carpeta"],
            ["fa-clipboard", "clipboard portapapeles checklist lista"],
            ["fa-pencil-square-o", "edit editar firmar sign"],
            ["fa-book", "book libro manual"],
            ["fa-print", "print imprimir impresora printer"],
            ["fa-archive", "archive archivo caja box"],
        ],
    },
    {
        label: _t("Communication"),
        icons: [
            ["fa-envelope-o", "mail correo email mensajeria messaging carta"],
            ["fa-comments-o", "chat comentarios mensajes messages"],
            ["fa-bullhorn", "announcement anuncio comunicado"],
            ["fa-phone", "phone telefono llamada call"],
            ["fa-paper-plane-o", "send enviar mensajeria"],
            ["fa-bell-o", "bell notificacion aviso alert"],
            ["fa-inbox", "inbox bandeja recepcion"],
            ["fa-truck", "truck camion envio shipping paqueteria mensajeria delivery"],
        ],
    },
    {
        label: _t("Work"),
        icons: [
            ["fa-briefcase", "briefcase trabajo work maletin"],
            ["fa-calendar", "calendar calendario vacaciones vacation ausencia leave"],
            ["fa-clock-o", "clock reloj horas hours tiempo time"],
            ["fa-wrench", "tool herramienta mantenimiento maintenance"],
            ["fa-laptop", "laptop ordenador computer it equipo"],
            ["fa-building-o", "building edificio oficina office"],
            ["fa-check-square-o", "check aprobacion approval tarea task"],
            ["fa-lightbulb-o", "idea sugerencia suggestion"],
            ["fa-shield", "security seguridad"],
            ["fa-exclamation-triangle", "incident incidencia problema warning"],
        ],
    },
];
// Same palette as the New Request cards (o_af_color_N in forms.css).
const COLORS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11];

/** Pick the icon and the color of a form: themed icons, a search box, colored dots. */
export class IconPicker extends Component {
    static template = "angels_forms.IconPicker";

    setup() {
        this.props = useProps(); // icon, color, onChange({icon, color}), autofocus
        this.state = useState({ query: "" });
        this.colors = COLORS;
    }

    get groups() {
        const words = this.normalize(this.state.query).split(/\s+/).filter(Boolean);
        return ICON_GROUPS.map((group) => ({
            label: group.label,
            icons: group.icons
                .filter(([icon, keywords]) => {
                    const text = this.normalize(`${icon} ${keywords} ${group.label}`);
                    return words.every((word) => text.includes(word));
                })
                .map(([icon]) => icon),
        })).filter((group) => group.icons.length);
    }
    setQuery(query) {
        this.state.query = query;
    }
    normalize(text) {
        return text
            .toLowerCase()
            .normalize("NFD")
            .replace(/[̀-ͯ]/g, "");
    }
    pickIcon(icon) {
        this.props.onChange({ icon });
    }
    pickColor(color) {
        this.props.onChange({ color });
    }
}
