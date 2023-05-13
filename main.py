import cvat_sdk as cvat
import dash
import plotly.express as px
from dash import Dash, Input, Output, dcc, html
from environs import Env
from PIL import Image, ImageDraw


def draw_shapes(image: Image.Image, annotations: dict) -> Image.Image:
    image = image
    draw = ImageDraw.Draw(image)
    for shape in annotations:
        corners = [shape['points'][:6], shape['points'][2:]]
        figures = []
        for corner in corners:
            start = corner[:2]
            middle = corner[2:4]
            end = corner[4:]
            center = [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2]
            unknown = [2 * center[0] - middle[0], 2 * center[1] - middle[1]]
            figures.append([*start, *middle, *end, *unknown])

        new_corners = [[*figures[0][:4], *figures[1][6:]],
                       [*figures[1][4:6], *figures[1][2:4], *figures[0][6:]]]

        for corner in new_corners:
            start = corner[:2]
            middle = corner[2:4]
            end = corner[4:]
            center = [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2]
            unknown = [2 * center[0] - middle[0], 2 * center[1] - middle[1]]
            figures.append([*start, *middle, *end, *unknown])

        figures.append([
            *figures[0][:2], *figures[0][6:], *figures[3][6:], *figures[2][6:]
        ])

        if shape['type'] == 'polyline':
            for figure in figures:
                draw.polygon(figure, outline='#00ff00', width=1)
            draw.line(shape['points'], fill='#ff0000', width=1)
    return image


env = Env()
env.read_env('.env')

cvat_host = env.str('CVAT_HOST')
cvat_creds = (env.str('CVAT_USER'), env.str('CVAT_PASSWORD'))

project_id = 94
client = cvat.make_client(cvat_host)
client.login(cvat_creds)

app = Dash(__name__)
server = app.server

project = client.projects.retrieve(project_id)
task_ids = [{
    'label': f'{task.id}: {task.name}',
    'value': task.id
} for task in sorted(project.get_tasks(), key=lambda x: x.id)]

app.layout = html.Div([
    html.Div(
        [
            html.P('Task select:'),
            dcc.Dropdown(options=task_ids,
                         value=task_ids[0]['value'],
                         id="task-id-dropdown",
                         clearable=False,
                         placeholder="Select task",
                         style={
                             'width': 400,
                             'margin': '0 auto'
                         }),
            html.P('Job select:'),
            dcc.Dropdown(id="job-id-dropdown",
                         clearable=False,
                         placeholder="Select job",
                         style={
                             'width': 400,
                             'margin': '0 auto'
                         }),
            html.P('Выбор фрейма:'),
            dcc.Input(id="frame-id-input",
                      type="number",
                      step=1,
                      placeholder=0,
                      inputMode='numeric',
                      style={
                          'height': 32,
                          'width': 400,
                          'margin': '0 auto'
                      })
        ],
        style={
            'display': 'flex',
            'flex-direction': 'row',
            'justify-content': 'flex-start'
        }),
    html.Div([
        dcc.Slider(0,
                   100,
                   value=0,
                   id='frame-id-slider',
                   tooltip={
                       "placement": "bottom",
                       "always_visible": True
                   })
    ]),
    dcc.Graph(id='image',
              responsive=True,
              config={
                  'fillFrame': True,
                  'autosizable': True,
                  'displayModeBar': True
              }),
    dcc.Store(id='segments', storage_type='session'),
    dcc.Store(id='job-annotations', storage_type='session')
],
                      style={'text-align': 'center'})


@app.callback(Output('job-id-dropdown', 'options'),
              Output('job-id-dropdown', 'value'), Output('segments', 'data'),
              Input('task-id-dropdown', 'value'))
def update_job_id_dropdown(selected_task):
    task = client.tasks.retrieve(selected_task)
    segments = {
        segment['jobs'][0]['id']: (
            segment['start_frame'],
            segment['stop_frame'],
        ) for segment in task.segments
    }
    jobs = list(sorted(segments.keys()))

    return jobs, jobs[0], segments


@app.callback(Output('frame-id-input', 'value', allow_duplicate=True),
              Output('frame-id-input', 'min'),
              Output('frame-id-input', 'max'),
              Output('frame-id-slider', 'value', allow_duplicate=True),
              Output('frame-id-slider', 'min'),
              Output('frame-id-slider', 'max'),
              Input('job-id-dropdown', 'value'),
              Input('segments', 'data'),
              prevent_initial_call=True)
def update_frame_id_inputs(selected_job, segments):
    selected_job = str(selected_job)
    start_frame = segments[selected_job][0]
    stop_frame = segments[selected_job][1]
    value = start_frame

    return value, start_frame, stop_frame, value, start_frame, stop_frame


@app.callback(Output('frame-id-input', 'value'),
              Output('frame-id-slider', 'value'),
              Input('frame-id-input', 'value'),
              Input('frame-id-slider', 'value'))
def sync_frame_id_inputs(input_value, slider_value):
    ctx = dash.callback_context
    trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
    value = input_value if trigger_id == "frame-id-input" else int(
        slider_value)

    return value, value


@app.callback(Output('job-annotations', 'data'),
              Input('job-id-dropdown', 'value'))
def get_job_annotations(job_id):
    job = client.jobs.retrieve(job_id)
    job_annotations = job.get_annotations()
    annotations = {}
    for shape in job_annotations.shapes:
        attributes = [attribute.value for attribute in shape.attributes]
        frame = shape.frame
        points = shape.points
        shape_type = shape.type.value
        id_exists = annotations.get(frame)
        shape_dict = {
            'attributes': attributes,
            'type': shape_type,
            'points': points
        }
        if not id_exists:
            annotations[frame] = [shape_dict]
        else:
            annotations[frame].append(shape_dict)

    return annotations


@app.callback(Output("image", "figure"), Input('task-id-dropdown', 'value'),
              Input('job-id-dropdown', 'value'),
              Input('frame-id-input', 'value'), Input('segments', 'data'),
              Input('job-annotations', 'data'))
def show_image(task_id, job_id, frame_id, segments, annotations):
    job = client.jobs.retrieve(job_id)
    job_frame_id = frame_id - segments[str(job_id)][0]
    image = job.get_frame(frame_id, quality='original')
    image = Image.open(image)  # type: ignore
    annotation = annotations.get(str(job_frame_id))
    if annotation:
        image = draw_shapes(image, annotation)

    figure = px.imshow(
        image,
        labels={
            'x': 'x, points',
            'y': 'y, points'
        },
        title=
        f'''<a href="{cvat_host}/tasks/{task_id}/jobs/{job_id}?frame={frame_id}">To CVAT farme</a>''',
        width=image.width,
        aspect='auto',
        template='seaborn',
    )
    figure.update_layout(autosize=False, width=image.width)

    return figure


if __name__ == '__main__':
    app.run_server(debug=True)
