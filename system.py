import cv2 as cv
import numpy as np

''' 
  Notes:
      When in BGR color space, each pixel's value is dependent on how much light is shining on them (the Blue, Green, Red values)
      When in HSV space, each pixel is described with with hue, saturation, and value
        Hue:          represents color
        Saturation:   represents the amount to which the color is mixed with white
        Value:        represents the amount to which the color is mixed with black
        
        
  TODO:
    1. [DONE] Read in video feed 
    2. [DONE] Foreground + Background detection
    3. [DONE] Discern the package type
    4. [DONE] Mark each package with a colored box indicating its type
    5. [DONE] Display UI with video feed + colored boxes + count
    7. [DONE] Test different scenarios and document success/failures
'''

# separate background from foreground for packages of type "bag" which are white/grey-ish
def apply_bag_thresholds(video_feed_bgr):
  hsv = cv.cvtColor(video_feed_bgr, cv.COLOR_BGR2HSV)
  sensitivity = 45
  low_white = (0, 0, 255-sensitivity)
  high_white = (255, sensitivity, 255)
  mask = cv.inRange(hsv, low_white, high_white)
  return cv.bitwise_and(video_feed_bgr, video_feed_bgr, mask=mask)
  

# separate background from foreground for packages of type "box" which are brown
def apply_box_thresholds(video_feed_bgr):
  hsv = cv.cvtColor(video_feed_bgr, cv.COLOR_BGR2HSV)
  low_brown = (6, 40, 0)
  high_brown = (23, 255, 255)
  mask = cv.inRange(hsv, low_brown, high_brown)
  return cv.bitwise_and(video_feed_bgr, video_feed_bgr, mask=mask)


# get the stats on the connected components for this frame
def get_connected_component_stats(video_frame):
    _, threshold = cv.threshold(cv.cvtColor(video_frame, cv.COLOR_BGR2GRAY), 0, 255, cv.THRESH_BINARY+cv.THRESH_OTSU)
    num_labels, _, stats, centroids = cv.connectedComponentsWithStats(threshold, 4, cv.CV_32S)
    
    # Aggregate connected component statistics
    conn_comp_stats = dict()
    for i in range(0, num_labels):
      if i == 0: # the first component is the background
        continue
      
      # extract the connected component statistics
      conn_comp_stats[i] = {
        "leftmost_x": stats[i, cv.CC_STAT_LEFT],
        "rightmost_x": stats[i, cv.CC_STAT_LEFT] + stats[i, cv.CC_STAT_WIDTH],
        "top_y": stats[i, cv.CC_STAT_TOP],
        "bottom_y": stats[i, cv.CC_STAT_TOP] - stats[i, cv.CC_STAT_HEIGHT],
        "width": stats[i, cv.CC_STAT_WIDTH],
        "height": stats[i, cv.CC_STAT_HEIGHT],
        "area": stats[i, cv.CC_STAT_AREA],
        "centroid": centroids[i]
      }
    return conn_comp_stats
 

# get total area for video frame/feed
def get_total_area(video_frame):
  _, threshold = cv.threshold(cv.cvtColor(video_frame, cv.COLOR_BGR2GRAY), 0, 255, cv.THRESH_BINARY+cv.THRESH_OTSU)
  num_labels, _, stats, _ = cv.connectedComponentsWithStats(threshold, 4, cv.CV_32S)
  total_area = 0
  for i in range(0, num_labels):
    total_area += stats[i, cv.CC_STAT_AREA]
  return total_area


# get the largest connected component in the detected connected components
def get_largest_component(components):
  return components[sorted([(components[index]["area"], index) for index in components.keys()], reverse=True)[0][1]]


# get the pixel value from a frame and pixel coordinate
def get_pixel_value_from_frame(frame, pixel_coord):
  for y, vals in enumerate(frame):
    for x, pixel_val in enumerate(vals):
      if (x, y) == (int(pixel_coord[0]), int(pixel_coord[1])):
        return pixel_val


# filter out connected components that are likely not packages
def filter_connected_components(total_area, components):
  actual_components = []
  for key in components.keys():
    component = components[key]
    # if a component is very small in area -- its likely not a package
    if float(component["area"] / total_area) < .015:
      continue
    actual_components.append(component)
  return actual_components


'''
  Mask the background that is not our tabletop.
  The values below were determined by a consistent domain + local testing.
'''
def apply_table_top_mask(video_feed_bgr):
  left_bound = 250
  right_bound = 1700
  bottom_bound = 200
  top_bound = 1200
      
  # mask any (x, y) coordinate that is not on our tabletop's rectangle (aka the background)
  mask = np.zeros(video_feed_bgr.shape[:2], np.uint8)
  mask[bottom_bound:top_bound, left_bound:right_bound] = 255
  res = cv.bitwise_and(video_feed_bgr, video_feed_bgr, mask = mask)
  return res


# outline detected packages so that our user can see what is being detected by the system
def outline_detected_packages(frame, thresholded_frame, package_type: str):
  thresholded_frame_gray = cv.cvtColor(thresholded_frame, cv.COLOR_BGR2GRAY)
  
  # determine the threshold based on package type (aka color)
  frame_gray_thresh = None
  if package_type == 'BAG':
    _, frame_gray_thresh = cv.threshold(thresholded_frame_gray, 210, 255, 0)
  elif package_type == 'BOX':
    _, frame_gray_thresh = cv.threshold(thresholded_frame_gray, 120, 185, 0)
    
  frame_contours, _ = cv.findContours(frame_gray_thresh, cv.RETR_TREE, cv.CHAIN_APPROX_SIMPLE)
  for c in frame_contours:
      if cv.contourArea(c) < 25000: # filter out any contours that arent big enough to be a package
        continue
      rect = cv.boundingRect(c)
      x,y,w,h = rect
      if package_type == 'BAG':
        cv.rectangle(frame, (x,y), (x+w,y+h), (0,255,0), 2) # green box
      if package_type == 'BOX':
        cv.rectangle(frame, (x,y), (x+w,y+h), (255,0,0), 2) # blue box
      cv.putText(frame, '{} Detected'.format(package_type), (x+w+10,y+h), 0, 0.3, (0,0,255))
      

# add the detected package count to the frame   
def add_package_counts(frame, bag_count, box_count):
  cv.putText(frame, 'Bag Count: {}'.format(bag_count), (20, 50), cv.FONT_HERSHEY_SIMPLEX, 2.0, (0,0,0), 3)
  cv.putText(frame, 'Box Count: {}'.format(box_count), (20, 120), cv.FONT_HERSHEY_SIMPLEX, 2.0, (0,0,0), 3)
  
  
cap = cv.VideoCapture('training_video/multiple_bags_and_boxes.mp4')

while cap.isOpened():
  # read in the video feed
  _, frame = cap.read()

  # get total area of video feed
  total_area = get_total_area(frame)
  
  # 1. apply a mask to the input frame such that we only perform object detection on our tabletop (not background)
  masked_frame = apply_table_top_mask(frame)

  # 2. perform foreground vs background detection for the two types of packages we are interested in
  bag_result = apply_bag_thresholds(masked_frame)
  box_result = apply_box_thresholds(masked_frame)
  
  # 3. filter out any detected connected components that are not the objects we are searching for
  bag_components = get_connected_component_stats(bag_result)
  actual_bag_components = filter_connected_components(total_area, bag_components)
  box_components = get_connected_component_stats(box_result)
  actual_box_components = filter_connected_components(total_area, box_components)
  
  # 4. outline detected packages
  outline_detected_packages(frame, bag_result, package_type='BAG')
  outline_detected_packages(frame, box_result, package_type='BOX')
  
  # 5. display the count of detected packages
  add_package_counts(frame, len(actual_bag_components), len(actual_box_components))
  
  # 6. show the output to the user
  cv.imshow('result', frame)

  # wait for user to quit feed
  if cv.waitKey(1) & 0xFF == ord('q'): # q is exit button
    break
      
      
cap.release()
cv.destroyAllWindows()
