from arcgis.gis import GIS
import pandas as pd
from dotenv import load_dotenv
import os
from shiny import App, reactive, render, ui
from datetime import date
import time

# to deploy
# rsconnect deploy shiny C:\Users\jared\Documents\brightwater\shinyapps\inventory --name brightwater --title inventory
BASEDIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASEDIR, ".env"))

t0 = time.time()
gis = GIS(
    "https://bwf.maps.arcgis.com/",
    username=os.getenv("UNAME"),
    password=os.getenv("PASSWORD"),
)

t1 = time.time()
invSurvey = (
    gis.content.get(os.getenv("INVSURVEY"))
    .layers[0]
    # .query()
    .query(
        out_fields="objectid,globalid,BrightWaterID,Namebwe,ReceivingSWE,Date,Products,NoPML1010,NoBWVeronicaBucketLabels"
    )
    .features
)
# fields
# NoBackpacks,NoIncubationBags,NoWhirlpaks,NoAABatteries,NoHealthClub,NoKisiKofiBooks,NoCalendars,NoCardboards,NoCertificatesCompletion,NoFlyers,NoKisiKofiFlyers,NoHats,NoPML1010,NoPML1510,NoPML2525,NoBWVeronicaBucketLabels,NoGAVeronicaBucketLabels,NoUVLights,NoEdManuals,NoTrainManuals,NoMarkers,NoPencils,NoPipettes,NoPosters,NoWashHandsPoster,NoPoloShirts,NoTeeShirts,NoWaterSpreaders,NoOasisTablets,NoColilert,NoPetrifilm,NoChlorineStrips50,NoBWBuckets,NoGABuckets

t2 = time.time()
orders = (
    pd.DataFrame([s.as_dict["attributes"] for s in invSurvey])
    .rename(columns={"objectid": "order_id"})
    .assign(status="Open", Date=lambda df_: pd.to_datetime(df_.Date,unit='ms').dt.strftime("%d %B, %Y"))
)
t3 = time.time()

print(t3 - t2, t2 - t1, t1 - t0)


inventory = pd.read_csv("inventory.csv", sep=";", names=["item", "quantity"])
# print(inventory)
app_ui = ui.page_fluid(
    ui.navset_tab(
        # Orders Tab
        ui.nav_panel(
            "Orders",
            ui.card(
                ui.card_header("Order List"),
                ui.input_radio_buttons(
                    "status_filter",
                    "Filter by Status:",
                    choices=["All", "Open", "Completed"],
                    selected="All",
                ),
                ui.output_data_frame("order_table"),
            ),
            ui.card(ui.card_header("Order Details"), ui.output_ui("order_details")),
        ),
        # Inventory Tab
        ui.nav_panel(
            "Inventory Management",
            ui.card(
                ui.card_header("Current Inventory"), ui.output_table("inventory_table")
            ),
            ui.card(
                ui.card_header("Update Inventory"),
                ui.input_select(
                    "item_select",
                    "Select Item",
                    choices=inventory["item"].tolist(),
                    width="100%",
                ),
                ui.input_numeric(
                    "new_quantity", "New Quantity", value=0, min=0, width="100%"
                ),
                ui.input_action_button(
                    "update_inventory", "Update", class_="btn-primary w-100"
                ),
            ),
        ),
    )
)


def server(input, output, session):
    # Reactive values for data management
    orders_rv = reactive.value(orders)
    inventory_rv = reactive.value(inventory)
    selected_order = reactive.value(None)

    @render.data_frame
    def order_table():
        df = orders_rv.get()
        if input.status_filter() != "All":
            df = df[df["status"] == input.status_filter()]
        return render.DataTable(
            df[["order_id", "Namebwe", "Date", "status"]], row_selection_mode="single"
        )

    @render.ui
    def order_details():
        selected = input.order_table_selected_rows()
        if not selected:
            return ui.p("Select an order to view details")

        order = orders_rv.get().iloc[selected[0]]

        elements = [
            ui.h4(f"Order #{order['order_id']}"),
            ui.p(f"Customer: {order['Namebwe']}"),
            ui.p(f"Date: {order['Date']}"),
            ui.p(f"Status: {order['status']}"),
            ui.p(ui.strong("Items:")),
            ui.p(order["Products"]),
        ]

        if order["status"] == "Open":
            elements.append(
                ui.input_action_button(
                    f"complete_{order['order_id']}",
                    "Mark as Completed",
                    class_="btn-success w-100",
                )
            )

        return ui.div(*elements)

    @render.table
    def inventory_table():
        return inventory_rv.get()

    def update_inventory_count():
        item = input.item_select()
        new_quantity = input.new_quantity()
        df = inventory_rv.get().copy()
        df.loc[df["item"] == item, "quantity"] = new_quantity
        inventory_rv.set(df)
        ui.notification_show(
            f"Updated {item} quantity to {new_quantity}", type="message", duration=3
        )

    @reactive.effect
    @reactive.event(input.update_inventory)
    def _():
        item = input.item_select()
        new_quantity = input.new_quantity()
        current_quantity = (
            inventory_rv.get()
            .loc[inventory_rv.get()["item"] == item, "quantity"]
            .iloc[0]
        )

        ui.modal_show(
            ui.modal(
                "Are you sure you want to update the inventory?",
                ui.p(
                    f"Change {item} quantity from {current_quantity} to {new_quantity}?"
                ),
                title="Confirm Inventory Update",
                easy_close=True,
                footer=ui.div(
                    ui.input_action_button(
                        "confirm_update", "Yes, Update", class_="btn-primary"
                    ),
                    ui.input_action_button(
                        "cancel_update", "Cancel", class_="btn-secondary"
                    ),
                ),
            )
        )

    @reactive.effect
    @reactive.event(input.confirm_update)
    def _():
        update_inventory_count()
        ui.modal_remove()

    @reactive.effect
    @reactive.event(input.cancel_update)
    def _():
        ui.modal_remove()

    # Handle order completion buttons
    def create_order_complete_handler(order_id):
        @reactive.effect
        @reactive.event(lambda: input[f"complete_{order_id}"]())
        def _():
            df = orders_rv.get().copy()
            df.loc[df["order_id"] == order_id, "status"] = "Completed"
            orders_rv.set(df)
            # Get customer name for the notification
            customer = df.loc[df["order_id"] == order_id, "Namebwe"].iloc[0]
            ui.notification_show(
                f"Order #{order_id} for {customer} marked as completed",
                type="message",
                duration=3,
            )

    # Create handlers for all possible order IDs
    for order_id in orders["order_id"]:
        create_order_complete_handler(order_id)


app = App(app_ui, server)
